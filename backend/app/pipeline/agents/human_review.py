"""P0 人在回路 (HITL) Agent —— 让用户审核并接受/修改中间产物。

灵感来自 "古风甜宠短剧" Skill 的"每阶段暂停审核"设计。

提供 3 个 Review 节点:
- step1_5_review: 审核 StoryAnalysis (角色 / 场景 / 情节)
- step2_5_review: 审核 Storyboard (镜头列表)
- step4_5_review: 审核 PromptPlan + 多版本 Prompt

审核指令 (state["human_feedback"]):
- "accept" → 继续
- "modify:<field>=<value>" → 修改字段后继续
- "reject:<reason>" → 触发回滚到 Step 3 (Step 4.5 reject 等同 Step 5 fail)
- "quit" → 终止

E2E 测试: 默认注入 "accept" 即可跑通。
"""

from __future__ import annotations

import json
from typing import Any

from ..graph.state import GraphState
from ..utils import get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


class HumanReviewAgent(BaseAgent):
    """人在回路审核节点基类。"""

    name = "human_review_base"
    temperature = 0.0

    # 子类覆盖: 审核哪个产物
    review_target: str = ""

    def __call__(self, state: GraphState) -> dict[str, Any]:
        logger.info("[%s] ⏸️  等待用户审核...", self.name)

        # 1. dump 当前产物到 stdout
        payload = self._extract_review_payload(state)
        logger.info(
            "[%s] 📋 当前产物:\n%s",
            self.name,
            json.dumps(payload, ensure_ascii=False, indent=2)[:1500],
        )

        # 2. 从 state["human_feedback"] 取下一条未消费的指令
        feedback = state.get("human_feedback") or []
        if not feedback:
            logger.warning("[%s] 无 human_feedback, 默认 accept", self.name)
            decision = "accept"
        else:
            decision = feedback.pop(0).strip()

        logger.info("[%s] 👤 用户决策: %s", self.name, decision)

        # 3. 应用决策 —— 每个 Review 节点写入自己的 decision 字段,
        #    避免 Step1 reject 误传到 Step4.5 的 conditional edge。
        decision_key = f"{self.name}_decision"  # 例: step1_5_review_decision
        # 归一化 decision 为 enum-like 字符串 (供 router 比较):
        #   "accept" | "quit" | "rejected" | "modified"
        if decision.startswith("reject:"):
            normalized = "rejected"
        elif decision.startswith("modify:"):
            normalized = "modified"
        else:
            normalized = decision  # accept / quit / 其它默认
        updates: dict[str, Any] = {
            "human_feedback": feedback,
            decision_key: normalized,  # 局部决策, 只供本节点的条件边读
            "pending_review": None,    # 全局标记 (Step 5 router 用), 默认清空
        }
        if normalized == "accept":
            updates["pending_review"] = None
        elif normalized == "quit":
            updates["pending_review"] = "quit"
        elif normalized == "modified":
            updates["pending_review"] = "modified"
            self._apply_modification(state, decision, updates)
        elif normalized == "rejected":
            # 全局标记 + 局部标记都置为 rejected,
            # 这样 _should_continue_after_review 读 step4_5_review_decision 即可精准判断本节点决策
            updates["pending_review"] = "rejected"
        else:
            logger.warning("[%s] 未识别指令, 默认 accept", self.name)

        self.audit(state, "user", f"[{self.name}] 决策: {decision}")
        return updates

    def _extract_review_payload(self, state: GraphState) -> dict[str, Any]:
        """子类覆盖: 提取要展示给用户的产物。"""
        return {}

    def _apply_modification(
        self, state: GraphState, decision: str, updates: dict[str, Any]
    ) -> None:
        """子类覆盖: 处理 modify 指令。"""
        # 格式: modify:<obj>.<field>=<value>
        # 例: modify:storyboard.shot_001.description=新描述
        try:
            payload = decision[len("modify:"):]
            path, value = payload.split("=", 1)
            obj_name, field_path = path.split(".", 1)
            target = state.get(obj_name)
            if target is None:
                logger.warning("[%s] 对象 %s 不存在", self.name, obj_name)
                return
            # 简化: 只支持一层 field 修改
            if "." not in field_path:
                setattr(target, field_path, value)
                logger.info("[%s] 修改 %s.%s = %s", self.name, obj_name, field_path, value)
            else:
                logger.warning("[%s] 嵌套字段修改暂不支持: %s", self.name, field_path)
        except Exception as e:
            logger.error("[%s] modify 解析失败: %s", self.name, e)


class Step1Review(HumanReviewAgent):
    """审核 Step 1 StoryAnalysis。"""

    name = "step1_5_review"
    review_target = "story_analysis"

    def _extract_review_payload(self, state: GraphState) -> dict[str, Any]:
        sa = state.get("story_analysis")
        if not sa:
            return {}
        return {
            "title": sa.title,
            "genre": sa.genre,
            "tone": sa.tone.value if hasattr(sa.tone, "value") else sa.tone,
            "characters": [
                {"id": c.character_id, "name": c.name, "role": c.role,
                 "visual_anchor_len": len(c.visual_anchor)}
                for c in sa.characters
            ],
            "scenes": [
                {"id": s.scene_id, "location": s.location}
                for s in sa.scenes
            ],
            "asset_count": len((state.get("asset_registry") or AssetRegistry_safe()).nodes),
        }


class Step2Review(HumanReviewAgent):
    """审核 Step 2 Storyboard。"""

    name = "step2_5_review"
    review_target = "storyboard"

    def _extract_review_payload(self, state: GraphState) -> dict[str, Any]:
        sb = state.get("storyboard")
        if not sb:
            return {}
        return {
            "title": sb.title,
            "shot_count": len(sb.shots),
            "total_duration_sec": sb.total_duration_sec,
            "shots": [
                {"id": s.shot_id, "duration": s.duration_sec,
                 "camera": s.camera.value, "framing": s.framing.value}
                for s in sb.shots
            ],
        }


class Step4Review(HumanReviewAgent):
    """审核 Step 4 PromptPlan + 多版本 Prompt。

    reject 行为: 清空 prompt_text + replan_count++, 让 Step 5 fail 触发回滚 Step 3。
    """

    name = "step4_5_review"
    review_target = "prompt_plan"

    def _extract_review_payload(self, state: GraphState) -> dict[str, Any]:
        plan = state.get("prompt_plan")
        if not plan:
            return {}
        # 用 getattr 兜底, 兼容 mock Pydantic 不识别新字段
        sample = ""
        if plan.shot_prompts and plan.shot_prompts[0].variants:
            v0 = plan.shot_prompts[0].variants[0]
            sample = getattr(v0, "prompt_text", "") or ""
            if sample:
                sample = sample[:200]
        return {
            "story_title": getattr(plan, "story_title", "") or "",
            "shot_count": len(plan.shot_prompts),
            "models": [m.value for m in plan.target_models],
            "sample_prompt": sample,
        }

    def __call__(self, state: GraphState) -> dict[str, Any]:
        # P0 HITL: 调用父类逻辑, 写入 step4_5_review_decision 字段,
        # _should_continue_after_review 路由读这一字段判断是否回滚 Step3。
        return super().__call__(state)


def AssetRegistry_safe():
    """兜底空 registry。"""
    from ..schemas import AssetRegistry
    return AssetRegistry()


step1_5_review = Step1Review()
step2_5_review = Step2Review()
step4_5_review = Step4Review()


__all__ = [
    "HumanReviewAgent",
    "Step1Review", "step1_5_review",
    "Step2Review", "step2_5_review",
    "Step4Review", "step4_5_review",
]
