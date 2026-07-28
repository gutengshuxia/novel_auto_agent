"""Step 3 Agent —— Prompt Planner。

输入: state["story_analysis"] + state["storyboard"]
输出: state["prompt_plan"]: PromptPlan

每个镜头 × 每个目标模型, 都先开一个空的 PromptVariant 占位,
Step 4 会逐条填充 prompt_text / negative_prompt / notes。
"""

from __future__ import annotations

from typing import Any

from ..graph.state import GraphState
from ..schemas import PromptPlan, PromptVariant, ShotPrompts
from ..schemas.enums import AspectRatio
from ..utils import get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


_STEP3_SYSTEM = """# Role

你是一位拥有 20 年以上经验的电影导演、摄影指导、AI 视频导演、**Prompt 规划专家**。

你的职责**不是**生成 Prompt, 你的职责是:
**分析导演分镜, 制定最适合 AI 视频模型执行的 Prompt 规划。**

禁止直接输出 Prompt。只输出 PromptPlan。

# 输入

Storyboard JSON, 含: 镜号 / 剧情节点 / Beat / 导演意图 / 人物 / 场景 / 光影 / 镜头 / 对白 / 道具。

# 工作目标

将电影分镜**转换成 AI 视频模型容易理解的执行计划**。
不是文学, 不是导演说明, 而是 Prompt 规划。

# 工作流程

## Step 1 — 分析镜头主体
- 主体是谁
- 主体在哪里
- 主体在干什么
- 镜头想表达什么

→ 输出到 subject_analysis { who, where, what, expression }

## Step 2 — 分析摄影
- 景别 (FramingStyle 枚举)
- 焦段 (如未提供则自动推断: wide=24mm / medium=50mm / close_up=85mm)
- 机位
- 构图 (三分法 / 中央构图 / 对角线 ...)
- 摄影机运动 (CameraMovement 枚举)
- 是否固定机位

## Step 3 — 拆分 Beat (必填)
**一个 Beat 不能遗漏, 必须保持原顺序。**

每个 Beat 输出:
- beat_id (beat_001 起)
- start_time / end_time (秒)
- action
- character (character_id)
- micro_expression (微表情)
- gaze (眼神方向)
- body_language (肢体动作)
- env_change (环境变化)
- dialogue (本 Beat 的对白, 可空)

→ 输出到 beats[] 列表

## Step 4 — 分析环境
天气 / 时间 / 光线 / 烟雾 / 灰尘 / 风 / 家具 / 背景动态

## Step 5 — 分析声音
环境音 / 动作音 / 对白 / 配乐 / 静默
→ 输出到 sound_design { ambient, sfx, dialogue, music, silence }

## Step 6 — 分析 Prompt 策略

根据镜头复杂程度自动选择:

| 策略 | 适用场景 | 长度 | 自由度 |
|---|---|---|---|
| **A (导演脚本版)** | 节奏优先, 让 AI 发挥 | 中 | 高 |
| **B (AI 执行版)** | 动作密集, 全要素锁定 | 长 | 低 |
| **C (导演调度版)** | 复杂调度, Beat 驱动 | 中 | 中 |

→ 输出到 prompt_strategy { length: short/medium/long, freedom: high/medium/low, style: A/B/C }

# Prompt 规划原则 (硬规则)

- **不要文学描写**
- **不要形容词堆积**
- **不要情绪词** (孤独/悲伤/绝望/压抑 ... 都禁)
- 全部转换成: 动作 / 摄影 / 环境 / 声音 / 节奏

# 输出 Schema (每个 shot_prompts) —— 精简版, 减少输出 token 数

{
  "shot_id": "shot_001",
  "subject_analysis": "一句话描述主体 (who/where/what/expression)",
  "beats": [
    { "beat_id": "b1", "t": "0-2s", "action": "...", "char": "char_001" }
  ],
  "sound_design": "环境音 + 关键音效, 1 句话",
  "variants": [ ... 5 个空 PromptVariant 占位 ... ],
  "dialogue": [...]
}

# 输出极简原则 (硬规则)
- subject_analysis 用 **1 个字符串**, 不要 4 个字段
- beats 每个最多 5 个字段 (beat_id / t / action / char / 可选 dialogue), 不要 10 个字段
- sound_design 用 **1 个字符串**, 不要 5 个字段
- 整体目标: 每个 shot 的 JSON 输出 **不超过 500 tokens**
- 7 个镜头总输出 **不超过 4000 tokens**, 避免被 max_tokens 截断

# 跨字段硬约束

- target_models 从 { runway, kling, jimeng, veo, pixverse } 选
- 每个 shot_prompts.variants **必须覆盖所有 target_models** (否则 Pydantic 校验失败)
- prompt_text / version_a/b/c 在 Step 3 阶段留空, Step 4 填充
- aspect_ratio 默认 16:9, 特殊镜头可改 9:16 或 21:9"""


class Step3Planner(BaseAgent):
    name = "step3_planner"
    system_prompt = _STEP3_SYSTEM
    output_schema = PromptPlan
    temperature = 0.4

    def __call__(self, state: GraphState) -> dict[str, Any]:
        analysis = state["story_analysis"]
        storyboard = state["storyboard"]
        logger.info("[Step 3] 开始 Prompt 规划 (%d 镜头 × %d 模型)",
                    len(storyboard.shots), len(analysis.target_models))

        user_prompt = (
            "## StoryAnalysis\n"
            f"```json\n{analysis.model_dump_json(indent=2)}\n```\n\n"
            "## Storyboard\n"
            f"```json\n{storyboard.model_dump_json(indent=2)}\n```\n\n"
            f"## 目标模型清单 (固定)\n{analysis.target_models}\n\n"
            "请为每个镜头生成完整的 PromptPlan。"
        )

        plan = self.invoke_llm_json(user_prompt, PromptPlan)
        plan.story_title = analysis.title or storyboard.title or "Untitled"

        # 兜底: 若 LLM 漏填某个模型, 用空 PromptVariant 补齐, 避免 PromptPlan 校验失败
        expected = set(m.value for m in plan.target_models)
        for sp in plan.shot_prompts:
            got = {v.target_model.value for v in sp.variants}
            for m in plan.target_models:
                if m.value not in got:
                    sp.variants.append(PromptVariant(
                        target_model=m,
                        aspect_ratio=AspectRatio.RATIO_16_9,
                        duration_sec=4.0,
                        notes="[auto-padded] Step 3 漏填, 待 Step 4 填充",
                    ))

        total = sum(len(sp.variants) for sp in plan.shot_prompts)
        self.audit(state, "assistant",
                   f"[step3] 产出 PromptPlan: {len(plan.shot_prompts)} 镜头, "
                   f"{len(plan.target_models)} 模型, 共 {total} 个变体")
        logger.info("[Step 3] ✅ 完成: %d 变体", total)
        return {"prompt_plan": plan}


step3_plan_prompts = Step3Planner()


__all__ = ["step3_plan_prompts", "Step3Planner"]
