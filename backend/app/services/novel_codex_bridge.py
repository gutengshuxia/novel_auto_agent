"""novel_codex_agent 桥接服务。

职责:
1. 从 Jellyfish DB 读取章节数据 (shots/entities)
2. 通过 JellyfishAdapter 转为 Pipeline 输入
3. 调用 PipelineEngine 执行 6 步 Pipeline
4. 将结果写回 DB (shot prompts / storyboard cards)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.studio import Chapter, Project, Shot, ShotDetail
from app.models.studio_shots import ShotCharacterLink
from app.models.studio_assets import Character, Costume

logger = logging.getLogger(__name__)

# ---- 全局任务存储 (简化版, 后续可迁移到 GenerationTask) ----
_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="novel_codex")


def _safe_read_task(task_id: str) -> dict[str, Any] | None:
    """线程安全读取任务快照。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        return dict(task) if task is not None else None


def _create_task(task_id: str, initial: dict[str, Any]) -> None:
    """线程安全创建任务。"""
    with _tasks_lock:
        _tasks[task_id] = dict(initial)


def _update_task_fields(task_id: str, **kwargs: Any) -> None:
    """线程安全更新任务字段。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is not None:
            task.update(kwargs)


class NovelCodexBridge:
    """桥接 Jellyfish DB 和 novel_codex_agent Pipeline。"""

    async def generate_for_chapter(
        self,
        db: AsyncSession,
        chapter_id: str,
        *,
        director_ids: list[str] | None = None,
        target_models: list[str] | None = None,
        enable_cards: bool = True,
        text_model_id: str | None = None,
    ) -> str:
        """
        异步启动 Pipeline 生成。

        Returns:
            task_id: 任务 ID (前端轮询用)
        """
        # 1. 从 DB 加载章节数据
        chapter_data = await self._load_chapter_data(db, chapter_id)
        if not chapter_data:
            raise ValueError(f"Chapter not found: {chapter_id}")

        # 2. 线程安全创建任务记录
        task_id = f"nc_{uuid.uuid4().hex[:12]}"
        _create_task(task_id, {
            "status": "pending",
            "progress": 0,
            "current_step": "",
            "chapter_id": chapter_id,
            "result": None,
            "error": None,
        })

        # 3. 在线程池中执行 Pipeline
        def _run_pipeline():
            try:
                from app.pipeline.engine import PipelineEngine
                from app.pipeline.adapters import JellyfishAdapter

                adapter = JellyfishAdapter()
                engine = PipelineEngine(enable_cards=enable_cards)

                # 构建 Pipeline 输入
                pipeline_input = adapter.build_pipeline_input(
                    chapter_id=chapter_id,
                    project_name=chapter_data["project_name"],
                    shots=chapter_data["shots"],
                    characters=chapter_data["characters"],
                    scenes=chapter_data.get("scenes"),
                    costumes=chapter_data.get("costumes"),
                    visual_style=chapter_data.get("visual_style", ""),
                    style=chapter_data.get("style", ""),
                    director_ids=director_ids,
                )

                # 进度回调
                def on_progress(step: str, pct: int):
                    _update_task_fields(task_id,
                        current_step=step, progress=pct, status="running")

                # 执行 Pipeline
                _update_task_fields(task_id, status="running", progress=5)
                result = engine.run(
                    story_text=pipeline_input["story_text"],
                    story_title=pipeline_input["story_title"],
                    cast_data=pipeline_input.get("cast_data"),
                    director_ids=pipeline_input.get("director_ids"),
                    progress_callback=on_progress,
                )

                result_dict = result.to_dict()
                _update_task_fields(task_id,
                    result=result_dict,
                    status="succeeded" if result.success else "failed",
                    progress=100,
                    error=result.error,
                )

                if result.success:
                    logger.info("Pipeline 成功: task=%s, %.1fs", task_id, result.elapsed_seconds)
                else:
                    logger.error("Pipeline 失败: task=%s, error=%s", task_id, result.error)

            except Exception as e:
                logger.exception("Pipeline 异常: task=%s", task_id)
                _update_task_fields(task_id, status="failed", error=str(e))

        # 4. 如果指定了 text_model_id, 从 DB 加载模型配置并设置 Pipeline LLM 覆盖
        llm_override_config = None
        if text_model_id:
            llm_override_config = await self._resolve_model_config(db, text_model_id)

        def _run_pipeline_with_override():
            try:
                if llm_override_config:
                    from app.pipeline.utils.llm import set_llm_override, clear_llm_override
                    set_llm_override(**llm_override_config)
                    logger.info("Pipeline 使用 DB 模型配置: provider=%s, model=%s",
                                llm_override_config.get("provider_key"), llm_override_config.get("model"))
                _run_pipeline()
            finally:
                if llm_override_config:
                    from app.pipeline.utils.llm import clear_llm_override
                    clear_llm_override()

        _executor.submit(_run_pipeline_with_override)
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询任务状态。"""
        task = _safe_read_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        return {
            "task_id": task_id,
            "status": task["status"],
            "current_step": task["current_step"],
            "progress": task["progress"],
            "error": task.get("error"),
        }

    async def get_task_result(
        self,
        task_id: str,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """获取任务结果, 完成后写回 DB。"""
        task = _safe_read_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if task["status"] not in ("succeeded", "failed"):
            return None

        result = task["result"]

        # 成功后写回 DB
        if task["status"] == "succeeded" and result:
            await self._write_back_results(db, task["chapter_id"], result)

        return result

    def _build_story_title(self, project_name: str, chapter_title: str | None = None) -> str:
        """构建 story_title (格式: 项目名 - 章节名)。"""
        if chapter_title:
            return f"{project_name} - {chapter_title}"
        return project_name

    async def _load_chapter_data(self, db: AsyncSession, chapter_id: str) -> dict[str, Any] | None:
        """从 DB 加载章节相关数据。"""
        chapter_stmt = select(Chapter).options(selectinload(Chapter.project)).where(Chapter.id == chapter_id)
        result = await db.execute(chapter_stmt)
        chapter = result.scalar_one_or_none()
        if not chapter:
            return None

        project = chapter.project
        project_name = project.name if project else chapter.title

        # 加载 shots
        shots_stmt = (
            select(Shot)
            .options(
                selectinload(Shot.detail),
                selectinload(Shot.character_links).selectinload(ShotCharacterLink.character),
            )
            .where(Shot.chapter_id == chapter_id)
            .order_by(Shot.index)
        )
        shots_rows = (await db.execute(shots_stmt)).scalars().all()

        shots = []
        character_ids: set[str] = set()
        for shot in shots_rows:
            detail = shot.detail
            char_names = [cl.character.name for cl in shot.character_links if cl.character]
            character_ids.update(cl.character_id for cl in shot.character_links if cl.character_id)

            shots.append({
                "id": shot.id,
                "index": shot.index,
                "title": shot.title,
                "script_excerpt": shot.script_excerpt,
                "camera_shot": getattr(detail, "camera_shot", "") if detail else "",
                "angle": getattr(detail, "angle", "") if detail else "",
                "movement": getattr(detail, "movement", "") if detail else "",
                "duration": getattr(detail, "duration", 0) if detail else 0,
                "description": getattr(detail, "description", "") if detail else "",
                "atmosphere": getattr(detail, "atmosphere", "") if detail else "",
                "action_beats": list(getattr(detail, "action_beats", []) or []) if detail else [],
                "character_names": char_names,
            })

        # 加载角色 + 服装
        characters = []
        costumes = []
        if character_ids:
            chars_stmt = (
                select(Character)
                .options(selectinload(Character.costume), selectinload(Character.actor))
                .where(Character.id.in_(character_ids))
            )
            chars_rows = (await db.execute(chars_stmt)).scalars().all()

            costume_ids: set[str] = set()
            for char in chars_rows:
                char_data = {
                    "id": char.id,
                    "name": char.name,
                    "description": char.description,
                    "actor_name": char.actor.name if char.actor else "",
                    "costume_id": char.costume_id,
                    "costume_description": char.costume.description if char.costume else "",
                }
                characters.append(char_data)
                if char.costume_id:
                    costume_ids.add(char.costume_id)

            if costume_ids:
                cos_stmt = select(Costume).where(Costume.id.in_(costume_ids))
                cos_rows = (await db.execute(cos_stmt)).scalars().all()
                costumes = [
                    {"id": c.id, "name": c.name, "description": c.description}
                    for c in cos_rows
                ]

        return {
            "project_name": project_name,
            "visual_style": getattr(project, "visual_style", "") if project else "",
            "style": getattr(project, "style", "") if project else "",
            "shots": shots,
            "characters": characters,
            "costumes": costumes,
        }

    async def _resolve_model_config(self, db: AsyncSession, model_id: str) -> dict[str, Any] | None:
        """从 DB 加载模型配置, 返回 set_llm_override() 所需的参数 dict。"""
        from app.models.llm import Model, Provider
        from sqlalchemy import select

        # 加载 model + provider
        model = await db.get(Model, model_id)
        if not model:
            logger.warning("Model not found: %s, 回退到 .env 配置", model_id)
            return None

        stmt = select(Provider).where(Provider.id == model.provider_id)
        provider = (await db.execute(stmt)).scalar_one_or_none()
        if not provider:
            logger.warning("Provider not found for model: %s", model_id)
            return None

        # 判断协议类型 (根据 provider name 映射)
        provider_name = provider.name.lower()
        protocol = "anthropic" if "claude" in provider_name or "anthropic" in provider_name else "openai"

        # 映射 provider key (用于 Pipeline 的 PROVIDER_PRESETS 兼容)
        provider_key_map = {
            "openai": "openai", "chatgpt": "openai",
            "deepseek": "deepseek",
            "qwen": "qwen", "通义": "qwen", "dashscope": "qwen", "阿里": "qwen", "百炼": "qwen",
            "zhipu": "zhipu", "智谱": "zhipu", "glm": "zhipu",
            "kimi": "kimi", "moonshot": "kimi", "月之暗面": "kimi",
            "doubao": "doubao", "豆包": "doubao", "火山": "doubao",
            "yi": "yi", "零一万物": "yi",
            "gemini": "gemini", "google": "gemini",
            "claude": "claude", "anthropic": "claude",
        }
        provider_key = None
        for alias, key in provider_key_map.items():
            if alias in provider_name:
                provider_key = key
                break

        return {
            "api_key": provider.api_key,
            "base_url": provider.base_url,
            "model": model.name,
            "provider_key": provider_key,
            "protocol": protocol,
            "temperature": model.params.get("temperature"),
            "max_tokens": model.params.get("max_tokens"),
        }

    async def _write_back_results(
        self,
        db: AsyncSession,
        chapter_id: str,
        result: dict[str, Any],
    ) -> None:
        """将 Pipeline 结果写回 DB。"""
        if not result.get("success") or not result.get("prompt_plan"):
            return

        from app.pipeline.adapters import JellyfishAdapter
        adapter = JellyfishAdapter()

        # 加载 shots 用于映射
        shots_stmt = select(Shot).where(Shot.chapter_id == chapter_id).order_by(Shot.index)
        shots_rows = (await db.execute(shots_stmt)).scalars().all()
        shots = [{"id": s.id, "index": s.index} for s in shots_rows]

        commands = adapter.build_write_back_commands(result, chapter_id, shots)

        for cmd in commands:
            shot_id = cmd["shot_id"]
            updates = cmd["updates"]

            # 更新 ShotDetail
            detail_stmt = select(ShotDetail).where(ShotDetail.id == shot_id)
            detail = (await db.execute(detail_stmt)).scalar_one_or_none()
            if detail:
                # 写入 description 字段 (作为 video prompt 存储)
                if updates.get("video_prompt_kling"):
                    detail.description = updates["video_prompt_kling"]

        await db.commit()
        logger.info("写回 DB 完成: chapter=%s, %d 条命令", chapter_id, len(commands))


# 全局实例
bridge = NovelCodexBridge()
