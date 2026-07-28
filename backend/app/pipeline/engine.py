"""Pipeline 引擎 —— 供外部系统 (Jellyfish) 调用。

将 LangGraph 6 步 Pipeline 封装为可调用引擎，支持：
- 外部传入剧本文本直接执行
- 进度回调 (step_name, percent)
- 故事板卡片生成
- 结果序列化为 dict (方便跨系统传输)
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from .graph import build_graph
from .graph.state import GraphState
from .schemas import PromptPlan, StoryAnalysis, Storyboard
from .utils import (
    CastManager,
    StoryboardCardGenerator,
    export_prompts_to_excel,
    get_logger,
)

logger = get_logger(__name__)


# ---- Pipeline 步骤定义 ----
STEP_NAMES = [
    "step1_analyze",
    "step1_5_review",
    "step2_storyboard",
    "step2_5_review",
    "step3_plan_prompts",
    "step4_write_prompts",
    "step4_5_review",
    "step5_consistency_check",
    "step6_model_adapter",
]

STEP_PROGRESS = {
    "step1_analyze": 10,
    "step1_5_review": 15,
    "step2_storyboard": 25,
    "step2_5_review": 30,
    "step3_plan_prompts": 40,
    "step4_write_prompts": 60,
    "step4_5_review": 65,
    "step5_consistency_check": 80,
    "step6_model_adapter": 95,
}


@dataclass
class PipelineResult:
    """Pipeline 执行结果。"""

    success: bool = False
    storyboard: dict[str, Any] | None = None
    prompt_plan: dict[str, Any] | None = None
    story_analysis: dict[str, Any] | None = None
    consistency_report: dict[str, Any] | None = None
    storyboard_cards: list[dict[str, Any]] = field(default_factory=list)
    cast_data: dict[str, Any] | None = None
    director_ids: list[str] | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict (跨系统传输用)。"""
        return {
            "success": self.success,
            "storyboard": self.storyboard,
            "prompt_plan": self.prompt_plan,
            "story_analysis": self.story_analysis,
            "consistency_report": self.consistency_report,
            "storyboard_cards": self.storyboard_cards,
            "cast_data": self.cast_data,
            "director_ids": self.director_ids,
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
        }


class PipelineEngine:
    """封装 LangGraph Pipeline 为可调用引擎。

    用法:
        engine = PipelineEngine()
        result = engine.run(
            story_text="...",
            story_title="第001章",
            director_ids=["wongkarwai-perspective"],
        )
        if result.success:
            print(result.prompt_plan)
    """

    def __init__(
        self,
        *,
        enable_cards: bool = True,
        max_replans: int = 3,
    ):
        self.enable_cards = enable_cards
        self.max_replans = max_replans
        self._graph = build_graph()

    def run(
        self,
        story_text: str,
        story_title: str,
        *,
        cast_data: dict[str, Any] | None = None,
        director_ids: list[str] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> PipelineResult:
        """
        执行完整 Pipeline。

        Args:
            story_text: 剧本文本
            story_title: 标题
            cast_data: 已有演员表 (可选, 从 cast.json 加载)
            director_ids: 导演风格列表 (可选)
            progress_callback: 进度回调 (step_name, percent)

        Returns:
            PipelineResult: 包含所有产物的结果对象
        """
        start_time = time.time()

        def _notify(step: str, pct: int):
            if progress_callback:
                try:
                    progress_callback(step, pct)
                except Exception:
                    pass

        try:
            # ---- 构建初始状态 ----
            initial_state: GraphState = {
                "story_text": story_text,
                "story_title": story_title,
                "max_replans": self.max_replans,
                "replan_count": 0,
                "story_analysis": None,
                "storyboard": None,
                "prompt_plan": None,
                "consistency_report": None,
                "final_outputs": None,
                "messages": [],
                "cast_data": cast_data or {},
                "chapter_title": story_title,
            }

            # 导演风格
            if director_ids:
                initial_state["director_ids"] = director_ids

            _notify("start", 5)
            logger.info("=== PipelineEngine 启动: %s ===", story_title)

            # ---- 执行 Pipeline ----
            final_state = self._graph.invoke(initial_state)

            _notify("pipeline_done", 90)

            # ---- 提取产物 ----
            storyboard: Storyboard | None = final_state.get("storyboard")
            prompt_plan: PromptPlan | None = final_state.get("prompt_plan")
            story_analysis: StoryAnalysis | None = final_state.get("story_analysis")
            consistency_report = final_state.get("consistency_report")

            if not storyboard or not prompt_plan:
                return PipelineResult(
                    success=False,
                    error="Pipeline 未产出 storyboard 或 prompt_plan",
                    elapsed_seconds=time.time() - start_time,
                )

            # ---- 序列化产物 ----
            result = PipelineResult(
                success=True,
                storyboard=storyboard.model_dump() if hasattr(storyboard, "model_dump") else None,
                prompt_plan=prompt_plan.model_dump() if hasattr(prompt_plan, "model_dump") else None,
                story_analysis=story_analysis.model_dump() if hasattr(story_analysis, "model_dump") else None,
                consistency_report=dict(consistency_report) if consistency_report else None,
                cast_data=final_state.get("cast_data"),
                director_ids=final_state.get("director_ids"),
            )

            # ---- 生成故事板卡片 ----
            if self.enable_cards and storyboard and prompt_plan and story_analysis:
                try:
                    _notify("generating_cards", 92)
                    cards = self._generate_cards(
                        storyboard=storyboard,
                        prompt_plan=prompt_plan,
                        story_analysis=story_analysis,
                        cast_data=final_state.get("cast_data", {}),
                        director_ids=final_state.get("director_ids"),
                    )
                    result.storyboard_cards = cards
                    logger.info("故事板卡片已生成: %d 张", len(cards))
                except Exception as e:
                    logger.error("故事板卡片生成失败: %s", e)

            _notify("done", 100)
            result.elapsed_seconds = time.time() - start_time
            logger.info("=== PipelineEngine 完成 (%.1fs) ===", result.elapsed_seconds)
            return result

        except Exception as e:
            logger.error("Pipeline 执行失败: %s", e)
            traceback.print_exc()
            return PipelineResult(
                success=False,
                error=str(e),
                elapsed_seconds=time.time() - start_time,
            )

    def _generate_cards(
        self,
        storyboard: Storyboard,
        prompt_plan: PromptPlan,
        story_analysis: StoryAnalysis,
        cast_data: dict[str, Any],
        director_ids: list[str] | None,
    ) -> list[dict[str, Any]]:
        """生成故事板分镜卡片。"""
        card_generator = StoryboardCardGenerator(enable_image_generation=False)

        # 构建角色演员表
        character_sheets: dict[str, str] = {}
        for char in story_analysis.characters:
            char_sheet = (
                cast_data.get(char.name, {}).get("character_sheet")
                or getattr(char, "character_sheet", "")
                or getattr(char, "base_appearance", "")
                or ""
            )
            if char_sheet:
                character_sheets[char.name] = char_sheet

        cards: list[dict[str, Any]] = []
        for shot_prompt in prompt_plan.shot_prompts:
            # 获取场景描述
            scene_desc = ""
            if shot_prompt.shot_id in storyboard.shots:
                shot = storyboard.shots[shot_prompt.shot_id]
                scene_desc = getattr(shot, "location", "") or ""

            # 获取导演风格
            director_style = ""
            if director_ids:
                director_style = ", ".join(director_ids)

            # 获取视频 prompt
            video_prompt = ""
            if shot_prompt.variants:
                video_prompt = shot_prompt.variants[0].prompt_text or ""

            if video_prompt:
                shot_cards = card_generator.generate_cards_from_prompt(
                    shot_id=shot_prompt.shot_id,
                    video_prompt=video_prompt,
                    character_sheets=character_sheets,
                    scene_description=scene_desc,
                    director_style=director_style,
                )
                cards.extend(shot_cards)

        return cards


__all__ = ["PipelineEngine", "PipelineResult", "STEP_NAMES", "STEP_PROGRESS"]
