"""6 步 Agent 节点 —— 全部基于 BaseAgent。"""

from ._base import BaseAgent
from .director_styles.loader import (DirectorStyleLoader, list_directors, get_director_style, build_collaboration_prompt, CollaborationMode)
from .human_review import (
    HumanReviewAgent,
    Step1Review, step1_5_review,
    Step2Review, step2_5_review,
    Step4Review, step4_5_review,
)
from .step1_analyzer import Step1Analyzer, step1_analyze
from .step2_director import Step2Director, step2_storyboard
from .step3_planner import Step3Planner, step3_plan_prompts
from .step4_writer import Step4Writer, step4_write_prompts
from .step5_consistency import Step5ConsistencyChecker, step5_consistency_check
from .step6_adapter import Step6ModelAdapter, step6_model_adapter

__all__ = [
    "BaseAgent",
    # 6 业务节点
    "Step1Analyzer", "step1_analyze",
    "Step2Director", "step2_storyboard",
    "Step3Planner", "step3_plan_prompts",
    "Step4Writer", "step4_write_prompts",
    "Step5ConsistencyChecker", "step5_consistency_check",
    "Step6ModelAdapter", "step6_model_adapter",
    # P0: HITL 审核节点
    "HumanReviewAgent",
    "Step1Review", "step1_5_review",
    "Step2Review", "step2_5_review",
    # P3: ?????
    "DirectorStyleLoader",
    "list_directors",
    "get_director_style",
    "build_collaboration_prompt",
    "CollaborationMode",
    "Step4Review", "step4_5_review",
]
