"""Beat 规划 Schema：将镜头拆分为时间戳 Beat 序列。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Beat(BaseModel):
    """单个 Beat（时间戳动作单元）。"""

    model_config = ConfigDict(extra="forbid")

    beat_id: str = Field(..., description="Beat 编号，如 b1/b2/b3")
    start_time: float = Field(..., ge=0, description="起始时间（秒）")
    end_time: float = Field(..., ge=0, description="结束时间（秒）")
    action: str = Field(..., description="动作描述（行为化，禁止抽象情感词）")
    character: str = Field("", description="角色名（@引用）")
    micro_expression: str = Field("", description="微表情（可见肌肉动作）")
    gaze: str = Field("", description="眼神方向")
    body_language: str = Field("", description="肢体动作")
    env_change: str = Field("", description="环境变化")
    dialogue: str = Field("", description="本 Beat 对白（可空）")


class BeatPlanResult(BaseModel):
    """Beat 规划结果。"""

    model_config = ConfigDict(extra="forbid")

    subject_analysis: str = Field("", description="一句话描述主体 (who/where/what/expression)")
    beats: List[Beat] = Field(default_factory=list, description="Beat 序列")
    sound_design: str = Field("", description="声音设计（环境音+关键音效，1句话）")
    prompt_strategy: str = Field("B", description="Prompt 策略：A(导演脚本版)/B(AI执行版)/C(导演调度版)")
    total_duration: float = Field(0, description="总时长（秒）")


__all__ = ["Beat", "BeatPlanResult"]
