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
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="novel_codex")


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

        # 2. 创建任务记录
        task_id = f"nc_{uuid.uuid4().hex[:12]}"
        _tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "current_step": "",
            "chapter_id": chapter_id,
            "result": None,
            "error": None,
        }

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
                    _tasks[task_id]["current_step"] = step
                    _tasks[task_id]["progress"] = pct
                    _tasks[task_id]["status"] = "running"

                # 执行 Pipeline
                _tasks[task_id]["status"] = "running"
                _tasks[task_id]["progress"] = 5
                result = engine.run(
                    story_text=pipeline_input["story_text"],
                    story_title=pipeline_input["story_title"],
                    cast_data=pipeline_input.get("cast_data"),
                    director_ids=pipeline_input.get("director_ids"),
                    progress_callback=on_progress,
                )

                result_dict = result.to_dict()
                _tasks[task_id]["result"] = result_dict
                _tasks[task_id]["status"] = "succeeded" if result.success else "failed"
                _tasks[task_id]["progress"] = 100
                _tasks[task_id]["error"] = result.error

                if result.success:
                    logger.info("Pipeline 成功: task=%s, %.1fs", task_id, result.elapsed_seconds)
                else:
                    logger.error("Pipeline 失败: task=%s, error=%s", task_id, result.error)

            except Exception as e:
                logger.exception("Pipeline 异常: task=%s", task_id)
                _tasks[task_id]["status"] = "failed"
                _tasks[task_id]["error"] = str(e)

        _executor.submit(_run_pipeline)
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询任务状态。"""
        task = _tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        return {
            "task_id": task_id,
            "status": task["status"],
            "current_step": task["current_step"],
            "progress": task["progress"],
            "error": task["error"] or "",
        }

    async def get_task_result(
        self,
        task_id: str,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """获取任务结果 (含写回 DB 后的摘要)。"""
        task = _tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if task["status"] != "succeeded":
            return {
                "task_id": task_id,
                "status": task["status"],
                "error": task["error"] or "",
            }

        result = task["result"]
        chapter_id = task["chapter_id"]

        # 写回 DB
        await self._write_back_results(db, chapter_id, result)

        # 构建返回摘要
        from app.pipeline.adapters import JellyfishAdapter
        adapter = JellyfishAdapter()

        # 构建 shot_prompts 摘要
        shot_prompts = []
        write_back_cmds = adapter.build_write_back_commands(
            result, chapter_id,
            shots=task.get("_shots_cache", []),
        )
        for cmd in write_back_cmds:
            updates = cmd.get("updates", {})
            shot_prompts.append({
                "shot_id": cmd["shot_id"],
                "shot_index": cmd["shot_index"],
                "shot_title": "",
                "prompt_text": updates.get("video_prompt_kling", ""),
                "negative_prompt": updates.get("negative_prompt", ""),
                "model": "kling",
                "quality_score": updates.get("prompt_quality_score", 0.0),
            })

        # 构建 cards 摘要
        cards_cmds = adapter.build_storyboard_cards_commands(result, chapter_id)
        cards = [
            {
                "shot_id": c["shot_id"],
                "card_type": c["card_type"],
                "title": c["title"],
                "prompt": c["prompt"],
                "image_url": c.get("image_url", ""),
            }
            for c in cards_cmds
        ]

        overall_score = 0.0
        if result.get("consistency_report"):
            overall_score = float(result["consistency_report"].get("score", 0))

        return {
            "task_id": task_id,
            "status": "succeeded",
            "current_step": "done",
            "progress": 100,
            "shot_prompts": shot_prompts,
            "storyboard_cards": cards,
            "overall_score": overall_score,
            "cast_updated": bool(result.get("cast_data")),
            "elapsed_seconds": result.get("elapsed_seconds", 0.0),
            "error": "",
        }

    # ---- 内部方法 ----

    async def _load_chapter_data(
        self,
        db: AsyncSession,
        chapter_id: str,
    ) -> dict[str, Any] | None:
        """从 DB 加载章节完整数据。"""
        # 加载 chapter + project
        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.project))
            .where(Chapter.id == chapter_id)
        )
        chapter = (await db.execute(stmt)).scalar_one_or_none()
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
                # TODO: 当 ShotDetail 新增 video_prompt_kling/jimeng 字段后, 改用专用字段

        await db.commit()
        logger.info("写回 DB 完成: chapter=%s, %d 条命令", chapter_id, len(commands))


# 全局实例
bridge = NovelCodexBridge()
