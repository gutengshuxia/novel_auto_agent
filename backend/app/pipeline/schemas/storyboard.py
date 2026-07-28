"""Step 2 Schema —— 导演分镜 (Storyboard)。

输入: StoryAnalysis
输出: 一组有序的 Shot, 每条含运镜、景别、时长、镜头描述、出场角色、台词。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import FramingStyle, VisualStyle

# delivery_type 取值: 对白 / 旁白 / 音效
DeliveryType = Literal["dialogue", "voiceover", "sfx"]


class CameraMovement(str, Enum):
    """镜头运动 —— 题目明确要求的字段。"""
    STATIC = "static"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"           # 推
    DOLLY_OUT = "dolly_out"         # 拉
    TRACK_LEFT = "track_left"
    TRACK_RIGHT = "track_right"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    HANDHELD = "handheld"           # 手持抖动
    DRONE_AERIAL = "drone_aerial"   # 航拍


class DialogueLine(BaseModel):
    """镜头内的一句台词。"""

    character_id: str = Field(..., min_length=1)
    line: str = Field(..., min_length=1, description="台词原文, 可中文")
    emotion: str = Field(default="", description="情绪标签, 如 愤怒 / 哽咽 / 平静")
    delivery_type: DeliveryType = Field(
        default="dialogue",
        description="台词类型: dialogue=对白 / voiceover=旁白 / sfx=音效描述",
    )


class Shot(BaseModel):
    """单个镜头 —— Step 2 的基本单元, Step 3/4 会进一步包装 Prompt 变体。"""

    shot_id: str = Field(..., min_length=1, description="形如 shot_001")
    scene_id: str = Field(..., min_length=1, description="所属场景, 引用 StoryAnalysis.scenes[].scene_id")
    shot_index: int = Field(..., ge=1, description="镜头在故事中的顺序, 从 1 开始")
    duration_sec: float = Field(default=4.0, gt=0, le=60.0, description="建议时长(秒)")

    framing: FramingStyle = Field(default=FramingStyle.MEDIUM, description="景别")
    camera: CameraMovement = Field(default=CameraMovement.STATIC, description="镜头运动")

    description: str = Field(..., min_length=10, description="镜头描述: 画面内容、动作、构图")
    characters_in_shot: list[str] = Field(
        default_factory=list,
        description="出场的 character_id 列表, 引用 StoryAnalysis.characters[].character_id",
    )

    # ---- 道具清单 (Step 5 道具一致性审计依据) ----
    props_in_shot: list[str] = Field(
        default_factory=list,
        description="本镜头中出现的道具列表, 用于 Step 5 道具一致性审计 (例: 手机/香烟/打火机/钥匙)",
    )

    # ---- 题目要求的"台词" ----
    dialogue: list[DialogueLine] = Field(default_factory=list, description="本镜头的台词")

    visual_style_override: Optional[VisualStyle] = Field(
        default=None,
        description="视觉风格覆盖, 用于回忆杀/幻想等特殊镜头; None 表示沿用 StoryAnalysis.visual_style",
    )
    visual_focus: str = Field(default="", description="导演备注: 视觉重心/情绪焦点")

    @field_validator("shot_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("shot_id 只能包含字母数字、下划线、横线")
        return v


class Storyboard(BaseModel):
    """Step 2 最终产出。"""

    title: str = ""
    based_on_title: str = Field(default="", description="对应 Step 1 的故事标题")
    shots: list[Shot] = Field(..., min_length=1)
    total_duration_sec: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _compute_total_duration(self) -> "Storyboard":
        self.total_duration_sec = round(sum(s.duration_sec for s in self.shots), 2)
        return self

    @model_validator(mode="after")
    def _check_unique_shot_id_and_order(self) -> "Storyboard":
        ids = [s.shot_id for s in self.shots]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"shot_id 必须唯一, 重复: {dup}")
        # shot_index 顺序与列表顺序一致
        for idx, shot in enumerate(self.shots, start=1):
            if shot.shot_index != idx:
                raise ValueError(
                    f"shot_index 与 shots 列表顺序不一致: 位置 {idx} 的 shot_id={shot.shot_id} "
                    f"shot_index={shot.shot_index}"
                )
        return self

    def to_json_schema(self) -> dict[str, Any]:
        return self.model_json_schema()


__all__ = [
    "CameraMovement",
    "DeliveryType",
    "DialogueLine",
    "Shot",
    "Storyboard",
]
