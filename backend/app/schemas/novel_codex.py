"""novel_codex_agent Prompt 引擎集成 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NovelCodexGenerateRequest(BaseModel):
    """一键生成 Prompt 请求。"""

    chapter_id: str = Field(..., description="章节 ID", min_length=1)
    director_ids: list[str] | None = Field(None, description="导演风格 ID 列表 (可选)")
    target_models: list[str] = Field(
        default=["kling", "jimeng"],
        description="目标视频生成模型",
    )
    enable_storyboard_cards: bool = Field(
        True,
        description="是否同时生成故事板分镜卡片",
    )


class NovelCodexShotPromptRead(BaseModel):
    """单个镜头的 Prompt 生成结果。"""

    shot_id: str = Field(..., description="镜头 ID")
    shot_index: int = Field(..., description="镜头序号")
    shot_title: str = Field("", description="镜头标题")
    prompt_text: str = Field("", description="视频生成 Prompt")
    negative_prompt: str = Field("", description="负面提示词")
    model: str = Field("", description="目标模型 (kling/jimeng)")
    quality_score: float = Field(0.0, description="质量评分 (0-100)")


class NovelCodexCardRead(BaseModel):
    """故事板卡片结果。"""

    shot_id: str = Field(..., description="镜头 ID")
    card_type: str = Field(..., description="卡片类型 (character/scene/shot)")
    title: str = Field("", description="卡片标题")
    prompt: str = Field("", description="卡片提示词")
    image_url: str = Field("", description="图片 URL (可选)")


class NovelCodexResultRead(BaseModel):
    """Prompt 生成任务结果摘要。"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态 (pending/running/succeeded/failed)")
    current_step: str = Field("", description="当前执行步骤")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    shot_prompts: list[NovelCodexShotPromptRead] = Field(
        default_factory=list,
        description="各镜头 Prompt 列表",
    )
    storyboard_cards: list[NovelCodexCardRead] = Field(
        default_factory=list,
        description="故事板卡片列表",
    )
    overall_score: float = Field(0.0, description="整体质量评分")
    cast_updated: bool = Field(False, description="是否更新了演员表")
    elapsed_seconds: float = Field(0.0, description="执行耗时 (秒)")
    error: str = Field("", description="错误信息 (失败时)")
