"""Beat 规划 Agent：将镜头拆分为时间戳 Beat 序列。

移植自 Pipeline Step3_Planner 的 Beat 规划逻辑，适配 Jellyfish DB 数据。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.beat_planning import BeatPlanResult


_BEAT_PLANNING_SYSTEM = """\
你是一位拥有 20 年以上经验的电影导演、摄影指导、AI 视频导演、Prompt 规划专家。

你的职责**不是**生成 Prompt，而是：
**分析镜头信息，制定最适合 AI 视频模型执行的 Beat 规划。**

禁止直接输出 Prompt。只输出 BeatPlanResult。

# 输入

镜头信息 JSON，含：剧本摘录、镜头描述、景别、机位、运镜、氛围、情绪标签、时长、对白、角色、场景、道具。

# 工作目标

将镜头**转换成 AI 视频模型容易理解的 Beat 执行计划**。
不是文学，不是导演说明，而是 Beat 规划。

# 工作流程

## Step 1 — 分析镜头主体
- 主体是谁
- 主体在哪里
- 主体在干什么
- 镜头想表达什么
→ 输出到 subject_analysis（1句话）

## Step 2 — 拆分 Beat（必填）
**一个 Beat 不能遗漏，必须保持原顺序。**

每个 Beat 输出：
- beat_id (b1/b2/b3...)
- start_time / end_time（秒，整数或0.5步进）
- action（行为化描述，禁止抽象情感词）
- character（角色名）
- micro_expression（微表情，可见肌肉动作）
- gaze（眼神方向）
- body_language（肢体动作）
- env_change（环境变化）
- dialogue（本 Beat 对白，可空）

→ 输出到 beats[] 列表

## Step 3 — 分析声音
环境音 / 动作音 / 对白 / 配乐 / 静默
→ 输出到 sound_design（1句话）

## Step 4 — 选择 Prompt 策略

| 策略 | 适用场景 | 长度 | 自由度 |
|---|---|---|---|
| A (导演脚本版) | 节奏优先，让 AI 发挥 | 中 | 高 |
| B (AI 执行版) | 动作密集，全要素锁定 | 长 | 低 |
| C (导演调度版) | 复杂调度，Beat 驱动 | 中 | 中 |

→ 输出到 prompt_strategy

# 硬约束

- **不要文学描写**（比喻/拟人/排比/借代）
- **不要形容词堆积**
- **不要抽象情感词**（孤独/悲伤/绝望/压抑/纠结...都禁）
- 全部转换成：动作 / 摄影 / 环境 / 声音 / 节奏
- 时间戳格式：整数秒 [0-2s] 或带小数 [2.5-4s]（0.5步进）
- Beat 时间范围必须覆盖镜头总时长，不重叠不遗漏
- 每个 Beat 至少包含 action 字段

# 输出 JSON Schema

{
  "subject_analysis": "一句话描述主体",
  "beats": [
    {
      "beat_id": "b1",
      "start_time": 0,
      "end_time": 2,
      "action": "动作描述",
      "character": "角色名",
      "micro_expression": "微表情",
      "gaze": "眼神方向",
      "body_language": "肢体动作",
      "env_change": "环境变化",
      "dialogue": ""
    }
  ],
  "sound_design": "环境音 + 关键音效",
  "prompt_strategy": "B",
  "total_duration": 5
}
"""

_BEAT_PLANNING_TEMPLATE = """\
## 镜头信息

剧本摘录：{script_excerpt}
镜头标题：{title}
镜头描述：{shot_description}
景别：{camera_shot}
机位角度：{angle}
运镜：{movement}
氛围：{atmosphere}
情绪标签：{mood_tags}
时长：{duration}秒
对白摘要：{dialog_summary}

## 已确认实体上下文

角色：{character_context}
场景：{scene_context}
道具：{prop_context}
服装：{costume_context}

请为这个镜头生成完整的 BeatPlanResult JSON。
"""


class BeatPlanningAgent(AgentBase[BeatPlanResult]):
    """Beat 规划 Agent，输出时间戳 Beat 序列 + 声音设计 + Prompt 策略。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "script_excerpt", "title", "shot_description",
                "camera_shot", "angle", "movement",
                "atmosphere", "mood_tags", "duration", "dialog_summary",
                "character_context", "scene_context", "prop_context", "costume_context",
            ],
            template=_BEAT_PLANNING_TEMPLATE,
        )

    @property
    def output_model(self) -> type[BeatPlanResult]:
        return BeatPlanResult

    @property
    def system_prompt(self) -> str:
        return _BEAT_PLANNING_SYSTEM

    def extract(self, **kwargs: Any) -> BeatPlanResult:
        inp = self._prepare_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> BeatPlanResult:
        inp = self._prepare_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)

    def format_output(self, raw: str) -> BeatPlanResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return BeatPlanResult()
        return self._normalize(data)

    def _normalize(self, data: dict[str, Any]) -> BeatPlanResult:
        """规范化 LLM 输出，处理缺失字段和类型转换。"""
        beats = data.get("beats", [])
        normalized_beats = []
        for b in beats:
            if isinstance(b, dict):
                normalized_beats.append({
                    "beat_id": str(b.get("beat_id", f"b{len(normalized_beats)+1}")),
                    "start_time": float(b.get("start_time", 0)),
                    "end_time": float(b.get("end_time", 0)),
                    "action": str(b.get("action", "")),
                    "intensity": str(b.get("intensity", "mid")),
                    "character": str(b.get("character", "")),
                    "camera_instruction": str(b.get("camera_instruction", "")),
                    "micro_expression": str(b.get("micro_expression", "")),
                    "gaze": str(b.get("gaze", "")),
                    "body_language": str(b.get("body_language", "")),
                    "env_change": str(b.get("env_change", "")),
                    "vfx_emphasis": str(b.get("vfx_emphasis", "")),
                    "dialogue": str(b.get("dialogue", "")),
                })
        return BeatPlanResult(
            subject_analysis=str(data.get("subject_analysis", "")),
            action_philosophy=str(data.get("action_philosophy", "")),
            intensity_arc=str(data.get("intensity_arc", "")),
            beats=normalized_beats,
            sound_design=str(data.get("sound_design", "")),
            prompt_strategy=str(data.get("prompt_strategy", "B")),
            total_duration=float(data.get("total_duration", 0)),
        )

    @staticmethod
    def _prepare_input(kwargs: dict[str, Any]) -> dict[str, Any]:
        """确保所有模板变量都有值。"""
        defaults = {
            "script_excerpt": "", "title": "", "shot_description": "",
            "camera_shot": "", "angle": "", "movement": "",
            "atmosphere": "", "mood_tags": "", "duration": 0, "dialog_summary": "",
            "character_context": "", "scene_context": "",
            "prop_context": "", "costume_context": "",
        }
        for key, default in defaults.items():
            if key not in kwargs or kwargs[key] is None:
                kwargs[key] = default
        # mood_tags 列表转字符串
        if isinstance(kwargs.get("mood_tags"), list):
            kwargs["mood_tags"] = ", ".join(str(t) for t in kwargs["mood_tags"])
        return kwargs


__all__ = ["BeatPlanningAgent", "BeatPlanResult"]
