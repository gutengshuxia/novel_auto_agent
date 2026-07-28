"""LangGraph 共享状态 —— TypedDict,各节点增量更新。"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from ..schemas import AssetRegistry, PromptPlan, StoryAnalysis, Storyboard


class ConsistencyReport(TypedDict, total=False):
    """Step 5 一致性检查产出。"""
    passed: bool
    issues: list[str]
    suggestions: list[str]
    checked_at_node: str


class GraphState(TypedDict, total=False):
    # 输入
    story_text: str
    story_title: str
    max_replans: int

    # ---- P3 导演风格配置 ----
    director_ids: list[str]    # 选择的导演 ID 列表, 如 ['wongkarwai-perspective']
    collaboration_mode: str    # 协作模式: 'sequential' / 'debate_vote' / 'chairman
    replan_count: int

    # 各步骤产出 (Pydantic 模型实例)
    story_analysis: Optional[StoryAnalysis]
    storyboard: Optional[Storyboard]
    prompt_plan: Optional[PromptPlan]
    consistency_report: Optional[ConsistencyReport]

    # 最终输出
    final_outputs: Optional[dict[str, Any]]

    # LangGraph 审计用
    messages: list[dict[str, Any]]

    # ---- P3 资产锚点系统 ----
    asset_registry: Optional[AssetRegistry]

    # ---- P0 人在回路 (HITL) ----
    human_feedback: list[str]   # 用户每轮反馈, 例: ["accept", "modify:shot_001.description=新描述"]
    pending_review: Optional[str]   # 全局审核标记: "rejected" / "quit" / "modified" / None。
                                   # 供 Step 5 的 _should_replan router 读取, 判断是否整体回滚或终止。
    # 每个 Review 节点独立的决策字段 (避免 Step1 reject 误传到 Step4.5 的 conditional edge)
    step1_5_review_decision: Optional[str]   # step1_5_review 的局部决策
    step2_5_review_decision: Optional[str]   # step2_5_review 的局部决策
    step4_5_review_decision: Optional[str]   # step4_5_review 的局部决策 (其 conditional edge 读这一项)

    # ---- 全局演员表 (跨章节持久化) ----
    cast_data: Optional[dict[str, Any]]  # 从 cast.json 加载的全局演员表
    chapter_title: Optional[str]  # 当前章节标题, 用于服装索引
