"""Jellyfish 数据适配器 —— DB ↔ Pipeline 数据转换。

职责:
- 从 Jellyfish DB 模型读取章节上下文, 转为 PipelineEngine 输入
- 将 Pipeline 输出写回 Jellyfish DB (shots/shot_details)
- 不依赖 SQLAlchemy ORM, 只接收 dict 数据 (由 Jellyfish 桥接服务传入)

这样设计使得 novel_codex_agent 不需要直接依赖 Jellyfish 的数据库模型,
保持两个项目的松耦合。
"""

from __future__ import annotations

from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


class JellyfishAdapter:
    """在 Jellyfish 数据和 Pipeline 之间做数据转换。

    用法 (在 Jellyfish 桥接服务中):
        adapter = JellyfishAdapter()
        pipeline_input = adapter.build_pipeline_input(chapter_data)
        result = engine.run(**pipeline_input)
        write_back_commands = adapter.build_write_back_commands(result, chapter_data)
    """

    def build_pipeline_input(
        self,
        *,
        chapter_id: str,
        project_name: str,
        shots: list[dict[str, Any]],
        characters: list[dict[str, Any]],
        scenes: list[dict[str, Any]] | None = None,
        costumes: list[dict[str, Any]] | None = None,
        visual_style: str = "",
        style: str = "",
        director_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        将 Jellyfish 数据转为 PipelineEngine.run() 的输入参数。

        Args:
            chapter_id: 章节 ID
            project_name: 项目名称 (作为 story_title)
            shots: 镜头列表, 每项包含:
                {id, index, title, script_excerpt,
                 camera_shot, angle, movement, duration,
                 description, atmosphere, action_beats,
                 character_names: [...]}
            characters: 角色列表, 每项包含:
                {id, name, description, actor_name, costume_name, costume_description}
            scenes: 场景列表 (可选)
            costumes: 服装列表 (可选)
            visual_style: 项目画面风格
            style: 项目题材风格
            director_ids: 导演风格列表

        Returns:
            dict: 可直接传给 PipelineEngine.run() 的参数
        """
        # ---- 组装剧本文本 ----
        story_text = self._build_story_text(shots)

        # ---- 组装演员表 ----
        cast_data = self._build_cast_data(characters, costumes)

        logger.info(
            "JellyfishAdapter: chapter=%s, %d shots, %d characters",
            chapter_id, len(shots), len(characters),
        )

        return {
            "story_text": story_text,
            "story_title": project_name,
            "cast_data": cast_data,
            "director_ids": director_ids,
        }

    def build_write_back_commands(
        self,
        result: dict[str, Any],
        chapter_id: str,
        shots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        将 Pipeline 结果转为写回命令列表。

        Jellyfish 桥接服务拿到这些命令后, 按 shot_id 匹配 DB 记录并更新。

        Args:
            result: PipelineResult.to_dict() 的输出
            chapter_id: 章节 ID
            shots: 原始 shots 列表 (用于 shot_id 映射)

        Returns:
            list[dict]: 写回命令列表, 每项:
                {
                    "shot_id": "xxx",
                    "shot_index": 1,
                    "updates": {
                        "video_prompt_kling": "...",
                        "video_prompt_jimeng": "...",
                        "negative_prompt": "...",
                        "prompt_quality_score": 92.0,
                    }
                }
        """
        if not result.get("prompt_plan"):
            return []

        prompt_plan = result["prompt_plan"]
        shot_prompts = prompt_plan.get("shot_prompts", [])

        # 构建 shot_index → shot_id 映射 (兼容 index/shot_index, id/shot_id)
        index_to_id: dict[int, str] = {}
        for shot in shots:
            idx = shot.get("index") or shot.get("shot_index", 0)
            sid = shot.get("id") or shot.get("shot_id", "")
            if idx and sid:
                index_to_id[idx] = sid

        commands: list[dict[str, Any]] = []

        for sp in shot_prompts:
            shot_id_str = sp.get("shot_id", "")
            # 尝试从 shot_id 解析 index (格式: shot_001, shot_002, ...)
            shot_index = self._parse_shot_index(shot_id_str)

            # 匹配 DB 中的 shot_id
            db_shot_id = index_to_id.get(shot_index, "")
            if not db_shot_id:
                # 如果 index 匹配失败, 尝试直接用 shot_id_str
                db_shot_id = shot_id_str

            # 提取各模型的 prompt
            variants = sp.get("variants", [])
            kling_prompt = ""
            jimeng_prompt = ""
            negative_prompt = ""

            for v in variants:
                model = v.get("target_model", "") or v.get("model", "")
                if model == "kling":
                    kling_prompt = v.get("prompt_text", "")
                    negative_prompt = v.get("negative_prompt", "")
                elif model == "jimeng":
                    jimeng_prompt = v.get("prompt_text", "")
                    if not negative_prompt:
                        negative_prompt = v.get("negative_prompt", "")

            # 质量评分
            quality_score = 0.0
            if result.get("consistency_report"):
                quality_score = float(
                    result["consistency_report"].get("overall_score")
                    or result["consistency_report"].get("score", 0)
                )

            commands.append({
                "shot_id": db_shot_id,
                "shot_index": shot_index,
                "updates": {
                    "video_prompt_kling": kling_prompt,
                    "video_prompt_jimeng": jimeng_prompt,
                    "negative_prompt": negative_prompt,
                    "prompt_quality_score": quality_score,
                },
            })

        logger.info("JellyfishAdapter: 生成 %d 条写回命令", len(commands))
        return commands

    def build_storyboard_cards_commands(
        self,
        result: dict[str, Any],
        chapter_id: str,
    ) -> list[dict[str, Any]]:
        """
        将故事板卡片结果转为写入命令。

        Returns:
            list[dict]: 卡片写入命令, 每项:
                {"shot_id": "...", "type": "...", "title": "...", "prompt": "...", "image_url": "..."}
        """
        cards = result.get("storyboard_cards", [])
        commands: list[dict[str, Any]] = []

        for card in cards:
            commands.append({
                "shot_id": card.get("shot_id", ""),
                "card_type": card.get("type", ""),
                "title": card.get("title", ""),
                "prompt": card.get("prompt", ""),
                "image_url": card.get("image_url", ""),
            })

        return commands

    # ---- 内部方法 ----

    def _build_story_text(self, shots: list[dict[str, Any]]) -> str:
        """合并所有 shots 的 script_excerpt 为完整剧本文本。"""
        parts: list[str] = []
        for shot in sorted(shots, key=lambda s: s.get("index", 0)):
            excerpt = (shot.get("script_excerpt") or "").strip()
            if excerpt:
                parts.append(excerpt)
        return "\n\n".join(parts)

    def _build_cast_data(
        self,
        characters: list[dict[str, Any]],
        costumes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        从 Jellyfish entities 构建 Pipeline 的 cast_data 格式。

        cast_data 格式:
        {
            "角色名": {
                "character_sheet": "角色描述...",
                "costumes": {
                    "章节名": "服装描述..."
                }
            }
        }
        """
        # 构建 costume_id → costume 映射
        costume_map: dict[str, dict[str, Any]] = {}
        if costumes:
            for c in costumes:
                costume_map[c["id"]] = c

        cast_data: dict[str, Any] = {}

        for char in characters:
            name = char.get("name", "")
            if not name:
                continue

            # 构建角色描述
            desc_parts: list[str] = []
            char_desc = (char.get("description") or "").strip()
            if char_desc:
                desc_parts.append(char_desc)

            # 添加演员信息
            actor_name = (char.get("actor_name") or "").strip()
            if actor_name:
                desc_parts.append(f"演员: {actor_name}")

            character_sheet = "\n".join(desc_parts) if desc_parts else name

            # 构建服装信息
            costume_entry: dict[str, str] = {}
            costume_id = char.get("costume_id")
            if costume_id and costume_id in costume_map:
                costume = costume_map[costume_id]
                costume_name = costume.get("name", "")
                costume_desc = (costume.get("description") or "").strip()
                if costume_name:
                    costume_entry["default"] = f"{costume_name}: {costume_desc}" if costume_desc else costume_name
            elif char.get("costume_description"):
                costume_entry["default"] = char["costume_description"]

            cast_data[name] = {
                "character_sheet": character_sheet,
                "costumes": costume_entry,
            }

        return cast_data

    @staticmethod
    def _parse_shot_index(shot_id: str) -> int:
        """从 shot_id 解析序号 (如 'shot_001' → 1)。"""
        import re
        m = re.search(r"(\d+)", shot_id)
        return int(m.group(1)) if m else 0


__all__ = ["JellyfishAdapter"]
