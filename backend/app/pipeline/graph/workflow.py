"""LangGraph 工作流装配 —— 6 节点 + 条件回滚。

节点序列:
    step1_analyze -> step2_storyboard -> step3_plan_prompts
        -> step4_write_prompts -> step5_consistency_check
            -> step6_model_adapter (END)   若 passed
            -> step3_plan_prompts           若 !passed 且 未超 max_replans
            -> END                          若 !passed 且 已超 max_replans
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

# agents imported lazily inside build_graph()
from ..utils import get_logger
from .state import GraphState

logger = get_logger(__name__)


def _should_continue_after_review(state: GraphState) -> str:
    """step4_5_review 的条件路由。

    读取 step4_5_review_decision (per-node 字段), 避免被其他 Review 节点的 reject 误触发。
    - "rejected" → 回滚 Step 3
    - 其他 (accept / modify / quit 等) → 进入 Step 5 (Step 5 router 再处理 quit)
    """
    decision = state.get("step4_5_review_decision")
    # HumanReviewAgent 把 "reject:<reason>" 归一化为 "rejected",
    # router 比较的是归一化值。
    if decision == "rejected":
        logger.warning("[Router] HITL step4 reject → 回滚 step3_plan_prompts")
        # 增加 replan_count
        state["replan_count"] = state.get("replan_count", 0) + 1
        # 清空 prompt_text 让 Step 3+4 重做
        plan = state.get("prompt_plan")
        if plan:
            for sp in plan.shot_prompts:
                for v in sp.variants:
                    if hasattr(v, "prompt_text"):
                        v.prompt_text = ""
                    for attr in ("version_a", "version_b", "version_c"):
                        if hasattr(v, attr):
                            setattr(v, attr, "")
        return "step3"
    return "step5"


def _should_replan(state: GraphState) -> str:
    """Step 5 的条件路由: 通过 -> step6; 未通过 -> 回滚 step3 或 终止。

    P0 扩展: pending_review == "rejected" 视同未通过,触发回滚。
    P0 扩展: pending_review == "quit" 立即终止。
    """
    # P0: 用户 quit
    if state.get("pending_review") == "quit":
        logger.warning("[Router] 用户退出 -> 终止")
        return "step6_failed"

    report = state.get("consistency_report")
    replan_count = state.get("replan_count", 0)
    max_replans = state.get("max_replans", 3)

    # 缺报告视为节点异常,直接终止
    if not report:
        logger.error("[Router] consistency_report 缺失,终止流水线")
        return "step6_failed"

    passed = bool(report.get("passed"))

    # P0: review rejected -> 强制回滚
    if state.get("pending_review") == "rejected":
        passed = False
        logger.warning("[Router] 用户 reject -> 强制回滚")

    if passed:
        logger.info("[Router] 一致性通过 -> step6_model_adapter")
        return "step6"

    if replan_count < max_replans:
        logger.warning(
            "[Router] 一致性未通过 (回滚 %d/%d) -> 回滚至 step3_plan_prompts",
            replan_count + 1,
            max_replans,
        )
        return "step3"

    logger.error("[Router] 一致性未通过且已超最大回滚次数 -> 终止")
    return "step6_failed"


@lru_cache(maxsize=1)
def build_graph():
    """构建并编译 LangGraph,返回可调用的图。"""
    from ..agents import (step1_analyze,step1_5_review,step2_storyboard,step2_5_review,step3_plan_prompts,step4_write_prompts,step4_5_review,step5_consistency_check,step6_model_adapter)
    workflow = StateGraph(GraphState)

    # 节点
    workflow.add_node("step1_analyze", step1_analyze)
    workflow.add_node("step1_5_review", step1_5_review)
    workflow.add_node("step2_storyboard", step2_storyboard)
    workflow.add_node("step2_5_review", step2_5_review)
    workflow.add_node("step3_plan_prompts", step3_plan_prompts)
    workflow.add_node("step4_write_prompts", step4_write_prompts)
    workflow.add_node("step4_5_review", step4_5_review)
    workflow.add_node("step5_consistency_check", step5_consistency_check)
    workflow.add_node("step6_model_adapter", step6_model_adapter)

    # 入口
    workflow.set_entry_point("step1_analyze")

    # ---- P0: HITL 审核节点串入主流程 ----
    workflow.add_edge("step1_analyze", "step1_5_review")
    workflow.add_edge("step1_5_review", "step2_storyboard")
    workflow.add_edge("step2_storyboard", "step2_5_review")
    workflow.add_edge("step2_5_review", "step3_plan_prompts")
    workflow.add_edge("step3_plan_prompts", "step4_write_prompts")
    workflow.add_edge("step4_write_prompts", "step4_5_review")
    # step4_5_review 的条件路由: reject -> step3 (跳过 Step 5), 其他 -> step5
    workflow.add_conditional_edges(
        "step4_5_review",
        _should_continue_after_review,
        {
            "step5": "step5_consistency_check",
            "step3": "step3_plan_prompts",
        },
    )

    # 条件边: Step 5 -> step6 / step3 / END
    workflow.add_conditional_edges(
        "step5_consistency_check",
        _should_replan,
        {
            "step6": "step6_model_adapter",
            "step3": "step3_plan_prompts",
            "step6_failed": END,
        },
    )

    # Step 6 结束
    workflow.add_edge("step6_model_adapter", END)

    return workflow.compile()


__all__ = ["build_graph"]
