"""剧本分镜 Agent：ScriptDividerAgent"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase, _extract_json_from_text
from app.schemas.skills.script_processing import ScriptDivisionResult

_SCRIPT_DIVIDER_SYSTEM_PROMPT = """\
你是一位专业的\"剧本分镜师\"，精通影视镜头语言，同时具备导演视角。你的任务是将剧本/小说文本拆分为多个独立的镜头(Shot)，并为每个镜头提供丰富的视觉描述。

## 拆分原则（按优先级排序）

1. **场景切换**：地点发生变化时必须拆分（如从"客厅"到"街道"）
2. **时间跳跃**：时间发生明显变化时拆分（如从"白天"到"夜晚"、"三天后"）
3. **人物进出**：关键人物上场或离场导致场景氛围变化
4. **情节转折**：重大动作或情绪转折（如打斗开始/结束、告白、意外发生）
5. **节奏需要**：即使同一场景，如果信息量过大（超过 5-8 行），也应拆分为多个镜头以保持节奏

## 禁止的拆分方式

- ❌ 不要按段落/回车拆分
- ❌ 不要按句号/逗号等标点拆分
- ❌ 不要每句话一个镜头
- ❌ 不要机械地按固定行数拆分
- ❌ 不要只输出剧本摘录——必须同时提供画面描述和镜头语言

## 每个镜头必须提供的信息

### 基础信息
- **shot_name**: 用一句话描述核心画面/动作（如"陆沉在雨巷中奔跑"）
- **script_excerpt**: 该镜头对应的原文
- **time_of_day**: DAY/NIGHT/DAWN/DUSK/UNKNOWN

### 画面描述（必填）
- **description**: 描述观众在屏幕上会看到的画面内容，包括人物动作、表情、构图（<=100字）
  - 示例："陆沉身穿黑色风衣，在狭窄的雨巷中全力奔跑，雨水溅起，身后两道黑影紧追不舍"

### 镜头语言（必填，根据情节合理推断）
- **camera_shot**: 景别 — ECU(大特写)/CU(特写)/MCU(中近景)/MS(中景)/MLS(中远景)/LS(远景)/ELS(大远景)
  - 对话/表情 → CU/MCU；动作场面 → MS/MLS；环境交代 → LS/ELS
- **camera_angle**: 机位 — EYE_LEVEL(平视)/HIGH_ANGLE(俯拍)/LOW_ANGLE(仰拍)/BIRD_EYE(鸟瞰)/OVER_SHOULDER(过肩)
- **camera_movement**: 运镜 — STATIC(固定)/PAN(平移)/DOLLY_IN(推)/DOLLY_OUT(拉)/TRACK(轨道)/CRANE(摇臂)/HANDHELD(手持)
  - 默认 STATIC；追逐/紧张 → TRACK/HANDHELD；气势 → CRANE/DOLLY_IN

### 时长与氛围
- **duration**: 建议时长（秒），对话镜头 3-5s，动作镜头 5-10s，环境建立 8-15s
- **mood_tags**: 情绪标签数组，如 ["紧张", "悬疑"] 或 ["温馨", "怀旧"]
- **atmosphere**: 氛围描述（光线、色调、声音），如"昏暗路灯，冷色调，雨声和脚步声"

## 输出格式

只输出 JSON：
{
  "shots": [
    {
      "index": 1,
      "start_line": 1,
      "end_line": 8,
      "shot_name": "雨巷追逐",
      "script_excerpt": "原文...",
      "time_of_day": "NIGHT",
      "description": "陆沉身穿黑色风衣在雨巷中奔跑...",
      "camera_shot": "MLS",
      "camera_angle": "EYE_LEVEL",
      "camera_movement": "TRACK",
      "duration": 8,
      "mood_tags": ["紧张", "悬疑"],
      "atmosphere": "昏暗路灯，冷色调，雨声"
    }
  ],
  "total_shots": N
}
"""

SCRIPT_DIVIDER_PROMPT = PromptTemplate(
    input_variables=["script_text"],
    template="## 输入脚本\n{script_text}\n\n## 输出\n",
)


class ScriptDividerAgent(AgentBase[ScriptDivisionResult]):
    """剧本自动分镜：输入完整剧本文本，输出分镜列表。"""

    enable_thinking: bool = False

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_DIVIDER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_DIVIDER_PROMPT

    @property
    def output_model(self) -> type[ScriptDivisionResult]:
        return ScriptDivisionResult

    def format_output(self, raw: str) -> ScriptDivisionResult:
        """
        更强的兜底解析：
        LLM 可能输出：
        - 正常结构：{shots:[...], total_shots:N}
        - 包裹结构：{"ScriptDivisionResult": {...}}
        - 直接列表：[{...}, {...}]（视为 shots）
        """

        json_str = _extract_json_from_text(raw)
        data: Any = json.loads(json_str)

        if isinstance(data, list):
            data = {"shots": data}
        elif isinstance(data, dict) and "ScriptDivisionResult" in data:
            inner = data.get("ScriptDivisionResult")
            if isinstance(inner, list):
                data = {"shots": inner}
            elif isinstance(inner, dict):
                data = inner
            else:
                data = {"shots": []}

        if isinstance(data, dict):
            data = self._normalize(data)

        return self.output_model.model_validate(data)  # type: ignore[arg-type]

    def divide_script(self, *, script_text: str) -> ScriptDivisionResult:
        return self.extract(script_text=script_text)

    async def adivide_script(self, *, script_text: str) -> ScriptDivisionResult:
        return await self.aextract(script_text=script_text)

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """规范化脚本分割结果。"""
        data = dict(data)

        # 兼容：LLM 可能输出 {"ScriptDivisionResult": {...}} 或 {"ScriptDivisionResult": [...]}
        if "ScriptDivisionResult" in data:
            inner = data.get("ScriptDivisionResult")
            if isinstance(inner, list):
                data = {"shots": inner}
            elif isinstance(inner, dict):
                data = dict(inner)
            else:
                data = {"shots": []}

        if "shots" in data and isinstance(data["shots"], list):
            shots = []
            for idx, shot in enumerate(data["shots"]):
                shot_dict: dict[str, Any] = (
                    dict(shot) if isinstance(shot, dict) else {"script_excerpt": str(shot), "shot_name": ""}
                )
                if "index" not in shot_dict:
                    shot_dict["index"] = idx + 1
                # 兼容：LLM 可能用 title/shot_title 代替 shot_name
                if "shot_name" not in shot_dict:
                    if "title" in shot_dict:
                        shot_dict["shot_name"] = str(shot_dict.pop("title"))
                    elif "shot_title" in shot_dict:
                        shot_dict["shot_name"] = str(shot_dict.pop("shot_title"))
                shot_dict.setdefault("shot_name", "")
                # 严格对齐 ShotDivision：移除已废弃的弱语义字段，避免 extra="forbid" 校验失败
                shot_dict.pop("scene_name", None)
                shot_dict.pop("character_names_in_text", None)
                shot_dict.pop("character_ids", None)
                shots.append(shot_dict)
            data["shots"] = shots

        if "total_shots" not in data and "shots" in data:
            data["total_shots"] = len(data["shots"])

        return data

