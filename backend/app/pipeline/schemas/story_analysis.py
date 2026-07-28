"""Step 1 Schema —— 剧本分析 (Story Analysis)。

输入: 原始文本 (story_text)
输出: 结构化的角色清单、场景列表、情节摘要、视觉关键词、目标模型。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import MoodTone, TargetModel, VisualStyle

DEFAULT_TARGET_MODELS: list[TargetModel] = [
    TargetModel.KLING,
    TargetModel.JIMENG,
]


class Character(BaseModel):
    """角色清单条目 —— Step 1 输出的角色列表每一项。

    P1 扩展: visual_anchor + reference_image_url 用于锁定角色基准形象,
    防止 LLM 在多镜头生成中让角色"变脸"。
    """

    character_id: str = Field(..., min_length=1, description="角色唯一 ID, 形如 char_001")
    name: str = Field(..., min_length=1, description="角色显示名")
    role: str = Field(default="", description="角色定位, 如 主角 / 反派 / 导师 / 路人")
    appearance: str = Field(default="", description="外貌描述, 用于画面提示词")
    personality: str = Field(default="", description="性格特征, 用于台词与表演")
    visual_keywords: list[str] = Field(
        default_factory=list,
        description="与该角色强绑定的视觉关键词, 如 龙鳞 / 红发 / 银袍",
    )

    # ---- P1: 角色基准形象锚定 (防 LLM 漂移) ----
    visual_anchor: str = Field(
        default="",
        description=(
            "详细角色基准形象描述, 作为后续所有镜头 Prompt 的形象锁定."
            " 包含: 面部特征 / 发型发饰 / 服装款式与配色 / 标志性道具 / 整体气质."
            " Step 4 生成 Prompt 时会优先使用此字段, 而非简短的 appearance."
        ),
    )
    reference_image_url: str = Field(
        default="",
        description="角色参考图 URL (用户上传或 AI 生成的四视图), 用于资产锚点系统",
    )

    # ---- 演员表级完整描述 (Step 1 生成, Step 4 查表引用) ----
    character_sheet: str = Field(
        default="",
        description=(
            "演员表级完整描述 (>=150 字符), 包含: "
            "三视图式外貌描述 / 面部特写 / 配色板(发色/肤色/服装色值) / "
            "局部细节(配饰/道具) / 全身比例 / 气质风格。"
            "Step 4 生成 Prompt 时, 首次出现该角色需完整引用, "
            "后续镜头使用 @角色名 简写引用。"
        ),
    )

    @field_validator("character_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("character_id 只能包含字母数字、下划线、横线")
        return v

    @field_validator("visual_anchor")
    @classmethod
    def _anchor_min_length(cls, v: str) -> str:
        if v and len(v) < 30:
            raise ValueError(
                "visual_anchor 应 >=30 字符 (含形象描述), "
                "否则无法锁定多镜头一致性"
            )
        return v


class Scene(BaseModel):
    """场景描述 —— 故事中可独立成镜的环境单位。"""

    scene_id: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1, description="地点, 如 悬崖之上的古堡")
    time_of_day: str = Field(default="", description="时辰/天气, 如 深夜 / 黄昏雨后")
    description: str = Field(..., min_length=10, description="场景详细描述, 用于 Prompt 反推")
    characters: list[str] = Field(
        default_factory=list,
        description="出现在该场景中的 character_id 列表",
    )
    visual_keywords: list[str] = Field(default_factory=list)

    @field_validator("scene_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("scene_id 只能包含字母数字、下划线、横线")
        return v


class StoryAnalysis(BaseModel):
    """Step 1 最终产出 —— 整篇故事的解构结果。"""

    title: str = Field(default="", description="故事标题, 若原文未给出可为空")
    genre: str = Field(default="", description="题材, 如 奇幻 / 悬疑 / 爱情")
    tone: MoodTone = Field(default=MoodTone.NEUTRAL)
    visual_style: VisualStyle = Field(default=VisualStyle.CINEMATIC)
    target_models: list[TargetModel] = Field(
        default_factory=lambda: list(DEFAULT_TARGET_MODELS),
        description="需要为其生成 Prompt 的目标模型清单",
    )

    # ---- 题目要求的三大块 ----
    characters: list[Character] = Field(..., min_length=1, description="角色清单, 至少 1 个")
    scenes: list[Scene] = Field(..., min_length=1, description="场景描述, 至少 1 个")
    plot_summary: str = Field(..., min_length=20, description="情节摘要, 用于 Step 2 拆镜参考")

    visual_keywords: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_characters_in_scenes(self) -> "StoryAnalysis":
        """校验: scenes[].characters 中出现的 ID 都能在 characters[].character_id 找到。"""
        declared = {c.character_id for c in self.characters}
        orphan: list[str] = []
        for scene in self.scenes:
            for cid in scene.characters:
                if cid not in declared:
                    orphan.append(f"{scene.scene_id}->{cid}")
        if orphan:
            raise ValueError(
                f"scenes 引用了未声明的 character_id: {orphan}. "
                "请先在 characters 中声明, 再在 scenes.characters 中引用。"
            )
        return self

    def to_json_schema(self) -> dict[str, Any]:
        """导出 JSON Schema —— 可作为 LLM 的 response_format 或 system prompt 契约。"""
        return self.model_json_schema()


__all__ = [
    "Character",
    "Scene",
    "StoryAnalysis",
    "DEFAULT_TARGET_MODELS",
]
