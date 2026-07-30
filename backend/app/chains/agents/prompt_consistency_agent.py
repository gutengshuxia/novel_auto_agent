"""Prompt 一致性审计 Agent：11 维度审核 Prompt 质量。

移植自 Pipeline Step5_Consistency，适配 Jellyfish 数据。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from app.chains.agents.base import AgentBase, _extract_json_from_text


class DimensionStatus(BaseModel):
    """单个维度审计结果。"""
    status: str = Field(default="PASS", description="PASS / WARNING / ERROR")
    issues: list[str] = Field(default_factory=list)


class ConsistencyAuditResult(BaseModel):
    """一致性审计结果。"""
    passed: bool = Field(default=True, description="是否通过")
    overall_score: int = Field(default=100, ge=0, le=100, description="总体评分 0-100")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    optimized_prompt: str = Field(default="", description="修正后的 Prompt")

    # 11 维度
    story_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    character_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    scene_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    prop_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    action_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    camera_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    lighting_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    environment_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    audio_consistency: DimensionStatus = Field(default_factory=DimensionStatus)
    prompt_quality: DimensionStatus = Field(default_factory=DimensionStatus)
    negative_prompt: DimensionStatus = Field(default_factory=DimensionStatus)


_CONSISTENCY_SYSTEM = """\
你是一位拥有 20 年以上经验的场记总监、连续性导演 (Script Supervisor)、AI 视频 Prompt 质量审核专家。

你的职责**不是**生成 Prompt，而是**审核 Prompt**。

# 审核原则（重要！）

**宽松审核，抓大放小：**
- ✅ 只关注**实质性错误**：角色变脸、场景突变、道具凭空消失、动作物理不可能
- ✅ **允许合理细化**：Prompt 比原始描述多出的细节是**正常的 Prompt 工程细化**，不算不一致
- ✅ **允许中英文角色名**："Lu Chen" = "陆沉"，不算不一致
- ❌ 不要因为描述更详细就标记为 ERROR
- ❌ 不要把 WARNING 升级为 ERROR

# 审核维度（11 个）

1. **剧情一致性**：是否遗漏/删减/新增剧情，是否改变顺序
2. **人物一致性**：年龄/身高/发型/服装/肤色/饰品是否矛盾
3. **场景一致性**：地点/天气/时间/建筑/灯光是否矛盾
4. **道具一致性**：是否凭空出现/消失/左右手交换/颜色变化
5. **动作连续性**：动作是否符合人体运动，是否跳跃/重复/冲突
6. **摄影连续性**：镜头方向/人物朝向/180°规则/运镜冲突
7. **光影一致性**：太阳方向/灯光方向/光色/曝光/阴影
8. **环境连续性**：烟雾/风/雨/灰尘/背景
9. **声音连续性**：环境音/对白/动作音/音乐
10. **AI Prompt 质量**：容易理解/无歧义/无重复/符合 AI 模型习惯
11. **负面 Prompt**：是否包含必要禁止项

# ERROR 标准（严格）
- 角色外貌矛盾（如"黑发"变"金发"）
- 场景突变（如"医院"变"海滩"）
- 道具矛盾（如"手机"变"电脑"）
- 动作物理不可能

# WARNING 标准（非 ERROR）
- 描述细化（如"手机"→"旧款手机"）
- 修饰词添加（如"走廊"→"昏暗走廊"）
- 未明确左右手但无矛盾

# 输出 JSON

{
  "passed": true/false,
  "overall_score": 85,
  "confidence": 0.85,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"],
  "optimized_prompt": "修正后的 Prompt（如有）",
  "story_consistency": {"status": "PASS", "issues": []},
  "character_consistency": {"status": "PASS", "issues": []},
  "scene_consistency": {"status": "PASS", "issues": []},
  "prop_consistency": {"status": "PASS", "issues": []},
  "action_consistency": {"status": "PASS", "issues": []},
  "camera_consistency": {"status": "PASS", "issues": []},
  "lighting_consistency": {"status": "PASS", "issues": []},
  "environment_consistency": {"status": "PASS", "issues": []},
  "audio_consistency": {"status": "PASS", "issues": []},
  "prompt_quality": {"status": "PASS", "issues": []},
  "negative_prompt": {"status": "PASS", "issues": []}
}
"""

_CONSISTENCY_TEMPLATE = """\
## 镜头上下文

角色：{character_context}
场景：{scene_context}
道具：{prop_context}
服装：{costume_context}

## 镜头信息

剧本摘录：{script_excerpt}
镜头标题：{title}
景别：{camera_shot}
机位：{angle}
运镜：{movement}
氛围：{atmosphere}
时长：{duration}秒

## 相邻镜头

上一镜头：{previous_shot_title} - {previous_shot_end_state}
下一镜头：{next_shot_title} - {next_shot_start_goal}

## 待审核 Prompt

{prompt_text}

## 负面提示词

{negative_prompt}

请按 11 个维度逐一审核，输出 JSON。
"""


class PromptConsistencyAgent(AgentBase[ConsistencyAuditResult]):
    """Prompt 一致性审计 Agent。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "character_context", "scene_context", "prop_context", "costume_context",
                "script_excerpt", "title", "camera_shot", "angle", "movement",
                "atmosphere", "duration",
                "previous_shot_title", "previous_shot_end_state",
                "next_shot_title", "next_shot_start_goal",
                "prompt_text", "negative_prompt",
            ],
            template=_CONSISTENCY_TEMPLATE,
        )

    @property
    def output_model(self) -> type[ConsistencyAuditResult]:
        return ConsistencyAuditResult

    @property
    def system_prompt(self) -> str:
        return _CONSISTENCY_SYSTEM

    enable_thinking = False  # 审核不需要 thinking

    def extract(self, **kwargs: Any) -> ConsistencyAuditResult:
        inp = self._prepare_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> ConsistencyAuditResult:
        inp = self._prepare_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)

    def format_output(self, raw: str) -> ConsistencyAuditResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return ConsistencyAuditResult(passed=True, issues=["audit_parse_error"])

        # 解析维度状态
        dim_names = [
            "story_consistency", "character_consistency", "scene_consistency",
            "prop_consistency", "action_consistency", "camera_consistency",
            "lighting_consistency", "environment_consistency", "audio_consistency",
            "prompt_quality", "negative_prompt",
        ]
        dims = {}
        for name in dim_names:
            dim_data = data.get(name, {})
            if isinstance(dim_data, dict):
                dims[name] = DimensionStatus(
                    status=str(dim_data.get("status", "PASS")).upper(),
                    issues=[str(i) for i in dim_data.get("issues", [])],
                )
            else:
                dims[name] = DimensionStatus()

        # 综合判断
        critical_dims = {"story_consistency", "character_consistency", "scene_consistency", "prop_consistency", "action_consistency"}
        critical_errors = [d for d in dim_names if d in critical_dims and dims[d].status == "ERROR"]
        score = int(data.get("overall_score", 100))

        passed = data.get("passed", True)
        if critical_errors:
            passed = False
        elif score >= 60 and not critical_errors:
            passed = True

        return ConsistencyAuditResult(
            passed=passed,
            overall_score=score,
            confidence=float(data.get("confidence", 0.8)),
            issues=[str(i) for i in data.get("issues", [])],
            suggestions=[str(s) for s in data.get("suggestions", [])],
            optimized_prompt=str(data.get("optimized_prompt", "")),
            **dims,
        )

    @staticmethod
    def _prepare_input(kwargs: dict[str, Any]) -> dict[str, Any]:
        defaults = {
            "character_context": "", "scene_context": "", "prop_context": "", "costume_context": "",
            "script_excerpt": "", "title": "", "camera_shot": "", "angle": "", "movement": "",
            "atmosphere": "", "duration": 0,
            "previous_shot_title": "", "previous_shot_end_state": "",
            "next_shot_title": "", "next_shot_start_goal": "",
            "prompt_text": "", "negative_prompt": "",
        }
        for key, default in defaults.items():
            if key not in kwargs or kwargs[key] is None:
                kwargs[key] = default
        return kwargs


__all__ = ["PromptConsistencyAgent", "ConsistencyAuditResult"]
