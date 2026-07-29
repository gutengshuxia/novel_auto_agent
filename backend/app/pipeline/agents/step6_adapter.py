"""Step 6 Agent ?? ???? (Model-Specific Optimizer)?

??: state["prompt_plan"] + state["storyboard"] + state["story_analysis"]
??: state["final_outputs"]: ?????????????

Step 4 ??? 2 ?????? prompt_text, Step 6 ??????"???????":

| ??       | ???? |
|-----------|----------|
| Kling     | ????????? (?/?/?/?/?/?), ?????? |
| Jimeng    | ?????? (?? >=80 ?), ??????????? |

?? final_outputs ??:
{
  "by_model": {
    "kling": [{"shot_id": "shot_001", "prompt_text": "...", "negative_prompt": "..."}],
    "jimeng": [...],
  },
  "summary": { ... }
}
"""

from __future__ import annotations

import re
from typing import Any

from ..graph.state import GraphState
from ..schemas.enums import TargetModel
from ..utils import get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


# ----- 2 ??????? -----
def _optimize_kling(text: str, camera: str) -> str:
    """Kling: ?????????, ???????"""
    cam_zh = {
        "dolly_in": "????", "dolly_out": "????",
        "pan_left": "????", "pan_right": "????",
        "tilt_up": "????", "tilt_down": "????",
        "track_left": "????", "track_right": "????",
        "crane_up": "????", "crane_down": "????",
        "zoom_in": "????", "zoom_out": "????",
        "handheld": "????", "drone_aerial": "????",
        "static": "????",
    }
    zh = cam_zh.get(camera, "????")
    if zh not in text:
        return f"{text} ({zh} cinematic)"
    return text


def _optimize_jimeng(text: str, min_len: int = 80) -> str:
    """??: ????, ?????? >=80 ??"""
    if len(text) >= min_len:
        return text
    padding = "?????????, ????, ?????????, ??????????????"
    return f"{text} {padding}"


_OPTIMIZERS = {
    TargetModel.KLING.value: _optimize_kling,
    TargetModel.JIMENG.value: _optimize_jimeng,
}


class Step6ModelAdapter(BaseAgent):
    """2 ????? ?? ? prompt_text ????????

    ??? PromptVariant:
    - prompt_text <- optimize(prompt_text)
    """

    name = "step6_adapter"
    temperature = 0.0  # ?????, ?? LLM

    def __call__(self, state: GraphState) -> dict[str, Any]:
        storyboard = state.get("storyboard")
        plan = state.get("prompt_plan")
        analysis = state.get("story_analysis")
        if storyboard is None or plan is None or analysis is None:
            logger.error("[Step 6] 上游产物缺失, 无法继续")
            return {}
        logger.info("[Step 6] ?????? (2 ??)")

        shot_map = {s.shot_id: s for s in storyboard.shots}
        by_model: dict[str, list[dict[str, Any]]] = {m.value: [] for m in plan.target_models}

        optimized_count = 0

        for sp in plan.shot_prompts:
            shot = shot_map.get(sp.shot_id)
            camera = shot.camera.value if shot else "static"

            for variant in sp.variants:
                model_key = variant.target_model.value
                optimizer = _OPTIMIZERS.get(model_key)

                text = variant.prompt_text or ""
                if text and optimizer:
                    if model_key == TargetModel.KLING.value:
                        optimized = optimizer(text, camera)
                    else:
                        optimized = optimizer(text)
                else:
                    optimized = text

                variant.prompt_text = optimized
                if optimized:
                    optimized_count += 1

                by_model[model_key].append({
                    "shot_id": sp.shot_id,
                    "scene_id": shot.scene_id if shot else "",
                    "duration_sec": variant.duration_sec,
                    "aspect_ratio": variant.aspect_ratio.value,
                    "prompt_text": optimized,
                    "negative_prompt": variant.negative_prompt,
                    "camera": camera,
                })

        summary = {
            "story_title": plan.story_title or analysis.title,
            "total_shots": len(plan.shot_prompts),
            "models": list(by_model.keys()),
            "per_model_count": {m: len(items) for m, items in by_model.items()},
            "optimized_count": optimized_count,
            "replan_count": state.get("replan_count", 0),
            "consistency_passed": (state.get("consistency_report") or {}).get("passed", False),
        }

        final_outputs = {"by_model": by_model, "summary": summary}

        self.audit(state, "assistant",
                   f"[step6] 2 ??????, {optimized_count} ? Prompt ???")
        for m, items in by_model.items():
            logger.info("[Step 6]   %s: %d ??", m, len(items))
        return {"final_outputs": final_outputs}


step6_model_adapter = Step6ModelAdapter()


__all__ = ["step6_model_adapter", "Step6ModelAdapter"]