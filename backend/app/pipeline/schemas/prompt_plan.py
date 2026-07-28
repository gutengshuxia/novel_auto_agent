"""Step 3 Schema —— Prompt 规划。

输入: StoryAnalysis + Storyboard
输出: 每个镜头 × 多模型变体的占位结构。Step 4 会填充 prompt_text。

约束:
- shot_prompts 中的 shot_id 必须能在 Storyboard 中找到
- 每个 shot_prompts 必须覆盖所有 target_models
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from .enums import AspectRatio, TargetModel
from .storyboard import DialogueLine


class PromptStrategy(BaseModel):
    """Prompt 长度与自由度策略 (Step 3 选定)。"""

    length: str = Field(default="medium", description="short / medium / long")
    freedom: str = Field(default="medium", description="high / medium / low")
    style: str = Field(default="A", description="默认输出哪个版本: A=导演脚本 / B=AI执行 / C=导演调度")


class PromptVariant(BaseModel):
    """单镜头 × 单模型的 Prompt 变体。"""

    target_model: TargetModel
    prompt_text: str = Field(default="", description="Step 4 填充; Step 3 阶段可为空规划占位")
    negative_prompt: str = Field(default="", description="反向提示词")
    aspect_ratio: AspectRatio = Field(default=AspectRatio.RATIO_16_9)
    duration_sec: float = Field(default=4.0, gt=0, le=60.0)
    notes: str = Field(default="", description="导演备注 / 模型特殊参数提示")


class ShotPrompts(BaseModel):
    """单个镜头的所有变体。"""

    shot_id: str = Field(..., min_length=1)
    variants: list[PromptVariant] = Field(..., min_length=1)
    dialogue: list[DialogueLine] = Field(default_factory=list)


class PromptPlan(BaseModel):
    """Step 3 最终产出。"""

    story_title: str = ""
    target_models: list[TargetModel] = Field(
        default_factory=lambda: [
            TargetModel.KLING,
            TargetModel.JIMENG,
        ]
    )
    shot_prompts: list[ShotPrompts] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_unique_shot_ids(self) -> "PromptPlan":
        ids = [sp.shot_id for sp in self.shot_prompts]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"shot_prompts.shot_id 必须唯一, 重复: {dup}")
        return self

    @model_validator(mode="after")
    def _check_models_covered(self) -> "PromptPlan":
        """每个镜头都必须为每个目标模型生成一个 variant 槽位。"""
        expected = {m.value for m in self.target_models}
        missing_per_shot: list[str] = []
        for sp in self.shot_prompts:
            got = {v.target_model.value for v in sp.variants}
            gap = expected - got
            if gap:
                missing_per_shot.append(f"{sp.shot_id} 缺 {sorted(gap)}")
        if missing_per_shot:
            raise ValueError(
                "每个 shot_prompts 必须覆盖所有 target_models:\n  - "
                + "\n  - ".join(missing_per_shot)
            )
        return self

    def to_json_schema(self) -> dict[str, Any]:
        return self.model_json_schema()


__all__ = [
    "PromptStrategy",
    "PromptVariant",
    "ShotPrompts",
    "PromptPlan",
]
