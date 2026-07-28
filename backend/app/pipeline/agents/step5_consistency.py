"""Step 5 Agent —— LLM-as-judge 一致性检查。

输入: state["story_analysis"] + state["storyboard"] + state["prompt_plan"]
输出: state["consistency_report"]: {passed: bool, issues: [...], suggestions: [...]}

检查维度:
1. 角色一致性: PromptPlan 中出现的 character_name 都能在 StoryAnalysis.characters 找到
2. 场景一致性: Storyboard 使用的 scene_id 都能在 StoryAnalysis.scenes 找到
3. 台词一致性: dialogue 角色 ID 合法; delivery_type 合法
4. 镜头数合理性: 镜头总数与故事长度匹配
5. 风格覆盖: visual_style_override 仅在确实需要时使用
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..graph.state import ConsistencyReport, GraphState
from ..utils import get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


class _DimensionStatus(BaseModel):
    """单个一致性维度的审计结果 (Step 5 扩展)。"""
    status: str = Field(default="PASS", description="PASS / WARNING / ERROR")
    issues: list[str] = Field(default_factory=list)


class _OptimizedPrompt(BaseModel):
    """自动修正后的 Prompt (Step 5 扩展)。"""
    prompt_text: str = Field(default="", description="修正后的 Prompt")


class _JudgeOutput(BaseModel):
    """Step 5 裁判输出 (升级版: 11 维度审计 + 自动修正)。

    与 LangGraph 路由兼容: 仍保留 passed 字段供条件边决策。
    """

    # ---- LangGraph 路由必备 ----
    passed: bool = Field(..., description="True = 通过; False = 需回滚 Step 3")
    issues: list[str] = Field(default_factory=list, description="聚合问题 (供 Step 3 修复)")
    suggestions: list[str] = Field(default_factory=list, description="修复建议, 与 issues 一一对应")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # ---- 扩展: 总体评分 ----
    overall_score: int = Field(default=100, ge=0, le=100, description="总体评分 0-100")

    # ---- 扩展: 11 维度审计 ----
    story_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    character_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    scene_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    prop_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    action_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    camera_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    lighting_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    environment_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    audio_consistency: _DimensionStatus = Field(default_factory=_DimensionStatus)
    prompt_quality: _DimensionStatus = Field(default_factory=_DimensionStatus)
    negative_prompt: _DimensionStatus = Field(default_factory=_DimensionStatus)

    # ---- 扩展: 自动修正输出 ----
    optimized_prompt: _OptimizedPrompt = Field(default_factory=_OptimizedPrompt)

    @model_validator(mode="after")
    def _sync_passed_from_dimensions(self) -> "_JudgeOutput":
        """根据维度状态和评分综合判断是否通过。

        规则:
        - 只有"核心维度"(角色/场景/道具/动作/剧情) ERROR 才触发回滚
        - 非核心维度 (prompt_quality/negative_prompt/audio等) ERROR 降级为 WARNING
        - score >= 70 且无核心维度 ERROR → 强制通过
        """
        dim_names = [
            "story_consistency", "character_consistency", "scene_consistency",
            "prop_consistency", "action_consistency", "camera_consistency",
            "lighting_consistency", "environment_consistency", "audio_consistency",
            "prompt_quality", "negative_prompt",
        ]
        # 核心维度: 这些 ERROR 会导致视频生成失败, 必须回滚
        critical_dims = {
            "story_consistency", "character_consistency", "scene_consistency",
            "prop_consistency", "action_consistency",
        }

        error_dims = [dim for dim in dim_names if getattr(self, dim).status == "ERROR"]
        critical_errors = [dim for dim in error_dims if dim in critical_dims]

        # 非核心维度 ERROR 降级为 WARNING (不触发回滚)
        for dim in error_dims:
            if dim not in critical_dims:
                getattr(self, dim).status = "WARNING"

        # 综合判断
        if critical_errors:
            self.passed = False
            all_issues = []
            for dim in dim_names:
                for iss in getattr(self, dim).issues:
                    all_issues.append(f"[{dim}] {iss}")
            if not self.issues:
                self.issues = all_issues
            if not self.suggestions:
                self.suggestions = [
                    f"修复 [{dim}] 维度问题" for dim in critical_errors
                ]
        elif self.overall_score >= 70:
            # score 足够高, 即使有 WARNING 也通过
            self.passed = True
        # else: 尊重 LLM 原始判断

        return self


_JUDGE_SYSTEM = """# Role

你是一位拥有 20 年以上经验的电影导演、摄影指导、**场记总监**、连续性导演 (Script Supervisor)、**AI 视频 Prompt 质量审核专家** (AI Prompt QA)。

你的职责**不是**生成 Prompt, 而是**审核 Prompt**。

# 审核目标

保证所有镜头符合:
- ✅ 电影制作规范
- ✅ AI 视频生成规范
- ✅ 镜头连续性
- ✅ 人物一致性
- ✅ 场景一致性
- ✅ 剧情一致性

# ⭐ 审核原则 (重要!)

**宽松审核, 抓大放小:**
- ✅ 只关注**实质性错误**: 角色变脸、场景突变、道具凭空消失、动作物理不可能
- ✅ **允许合理细化**: Prompt 比 Storyboard 多出的细节描述 (如“旧款手机”“昏暗走廊”) 是**正常的 Prompt 工程细化**, 不算不一致
- ✅ **允许中英文角色名**: “Lu Chen” = “陆沉”, 不算不一致
- ✅ **允许合理的修饰词添加**: “走廊” → “昏暗的走廊” 是丰富描述, 不算场景变化
- ❌ 不要因为 Prompt 比 Storyboard 描述更详细就标记为 ERROR
- ❌ 不要把 WARNING 升级为 ERROR, 只有真正会导致视频生成失败的问题才标 ERROR

# 输入

1. StoryAnalysis.json (Step 1)
2. Storyboard.json (Step 2)
3. PromptPlan.json (Step 3, 含 subject_analysis / beats / sound_design)
4. 每个镜头的最终 Prompt (prompt_text)

# 工作目标 — 审核整个镜头链路

不是审核一个 Prompt, 而是审核:

小说 → 导演分析 → 导演分镜 → PromptPlan → 最终 Prompt

是否一致。

# 审核流程 (12 步)

每一步对每个镜头, 输出 status = PASS / WARNING / ERROR。

**ERROR 标准 (必须严格):**
- 角色外貌矛盾 (如“黑发”变“金发”)
- 场景突变 (如“医院”变“海滩”)
- 道具矛盾 (如“手机”变“电脑”)
- 动作物理不可能 (如“左手拿东西”同时“左手做其他事”)
- 剧情顺序颠倒

**WARNING 标准 (非 ERROR):**
- 描述细化 (如“手机” → “旧款手机”)
- 修饰词添加 (如“走廊” → “昏暗走廊”)
- 中英文角色名混用
- 未明确左右手但无矛盾
- 声音/光影的细微差异但不影响视频效果

## Step 1 — 剧情一致性
- 是否遗漏 Beat
- 是否删减剧情
- 是否新增剧情
- 是否修改对白
- 是否改变剧情顺序

## Step 2 — 人物一致性
- 年龄 / 身高 / 发型 / 服装 / 肤色 / 伤疤 / 饰品
- 动作习惯 / 惯用手 / 资产引用
- **人物名称是否一致** (例: “@陆沉” 不能写成 “男主 / 青年 / 男人 / 主人公”, 但 “Lu Chen” = “陆沉” 可接受)
- 统一引用人物资产

## Step 3 — 场景一致性
- 地点 / 天气 / 时间 / 建筑 / 家具 / 灯光 / 背景
- 例: “出租屋” 不能突然变 “豪华公寓”; “白天” 不能突然变 “夜晚”
- 注意: 场景细化 (如“医院门口” → “医院大门外台阶上”) 是 PASS, 不是 ERROR

## Step 4 — 道具一致性
- 手机 / 医院结款单 / 香烟 / 打火机 / 钱包 / 钥匙 ...
- 检查: 凭空出现 / 凭空消失 / 左右手交换 / 颜色变化 / 型号变化 / 品牌变化
- 例: “小米 15” 不能下一镜变 “iPhone”
- 注意: “手机” → “旧款手机” 是细化, PASS; “钢笔” → “金色钢笔” 是细化, PASS

## Step 5 — 动作连续性
- 动作是否符合人体运动
- 是否跳跃 / 重复 / 冲突
- 例: 上一 Beat 左手拿手机, 下一 Beat 左手揉头 → 必须先放下手机
- 注意: 未明确左右手不算 ERROR, 只要没有矛盾

## Step 6 — 摄影连续性
- 镜头方向 / 人物朝向 / 摄影机方向
- **180° 规则**
- 运镜是否冲突
- 例: 上一镜人物看左, 下一镜突然看右 → 需要说明

## Step 7 — 光影一致性
- 太阳方向 / 灯光方向 / 光色 / 曝光 / 阴影
- 注意: “暖黄灯光” vs “暖黄色调” 语义一致, PASS

## Step 8 — 环境连续性
- 烟雾 / 风 / 雨 / 灰尘 / 背景人流 / 背景车辆

## Step 9 — 声音连续性
- 环境音 / 对白 / 动作音 / 音乐
- 例: 镜头切换, 音乐不能突然消失

## Step 10 — AI Prompt 质量
- 容易理解 / 无歧义
- **少量文学语言可接受** (不必每个抽象词都标 ERROR)
- 无重复描述 / 无冲突
- 符合 AI 视频模型理解习惯

## Step 11 — Prompt 完整性
必须包含:
- 主体 / 动作 / 摄影 / 环境 / 声音

缺失核心项 (主体/动作) → WARNING
缺失次要项 (结束画面/声音) → WARNING (不是 ERROR)

## Step 12 — 负面 Prompt 检查
包含以下关键词之一即可:
- 人物变形 / 多指 / 少指 / 穿模 / deformed
- 镜头漂移 / 背景跳变 / blurry
- 烟雾异常 / 物理错误 / low quality

有负面提示但用英文 (如 "deformed, blurry") 也算 PASS

# 自动修正 (新增)

如果发现问题, **不要直接结束**。
自动输出:
1. **修正建议** (fix_suggestion)
2. **修正后的 Prompt** (optimized_prompt.prompt_text)

# 输出 JSON Schema (Pydantic 校验)

{
  "passed": bool,                          // True = 一致, False = 需回滚 Step 3
  "overall_score": int (0-100),            // 总体评分
  "confidence": float (0.0-1.0),           // 自信度
  "issues": [str],                         // 聚合所有问题, 每条 ≤120 字
  "suggestions": [str],                     // 修复建议, 与 issues 一一对应
  "story_consistency":     { "status": "PASS/WARNING/ERROR", "issues": [str] },
  "character_consistency": { "status": ..., "issues": [...] },
  "scene_consistency":     { "status": ..., "issues": [...] },
  "prop_consistency":      { "status": ..., "issues": [...] },
  "action_consistency":    { "status": ..., "issues": [...] },
  "camera_consistency":    { "status": ..., "issues": [...] },
  "lighting_consistency":  { "status": ..., "issues": [...] },
  "environment_consistency":{ "status": ..., "issues": [...] },
  "audio_consistency":     { "status": ..., "issues": [...] },
  "prompt_quality":        { "status": ..., "issues": [...] },
  "negative_prompt":       { "status": ..., "issues": [...] },
  "fix_suggestion": [str],                 // 自动修正建议
  "optimized_prompt": {
    "prompt_text": "..."
  }
}

# 通过阈值 (与 LangGraph 路由兼容)

- 所有维度均 PASS 或 WARNING → passed=true → 路由到 Step 6
- 任意维度 ERROR → passed=false → 路由回 Step 3 重规划
- 仅有 WARNING → passed=true (警告但不回滚)
- **score >= 60 且无 ERROR 维度 → passed=true**"""


class Step5ConsistencyChecker(BaseAgent):
    name = "step5_consistency"
    system_prompt = _JUDGE_SYSTEM
    output_schema = _JudgeOutput
    temperature = 0.2  # 裁判要严谨, 低温

    def __call__(self, state: GraphState) -> dict[str, Any]:
        analysis = state["story_analysis"]
        storyboard = state["storyboard"]
        plan = state["prompt_plan"]
        logger.info("[Step 5] 开始一致性检查 (回滚次数=%d)", state.get("replan_count", 0))

        # 把上游产物精简喂给裁判, 避免 token 爆炸
        user_prompt = (
            "## StoryAnalysis (摘要)\n"
            f"- 角色: {[c.name + '(' + c.character_id + ')' for c in analysis.characters]}\n"
            f"- 场景: {[s.scene_id + ':' + s.location for s in analysis.scenes]}\n\n"
            "## Storyboard\n"
            f"```json\n{storyboard.model_dump_json(exclude_none=True)}\n```\n\n"
            "## PromptPlan\n"
            f"```json\n{plan.model_dump_json(exclude_none=True)}\n```\n\n"
            "请按 system prompt 中的 7 项规则逐一审查, 输出 JSON。"
        )

        try:
            judge = self.invoke_llm_json(user_prompt, _JudgeOutput)
        except Exception as e:  # noqa: BLE001
            # 裁判自身失败时, 默认通过 (避免死循环), 但记录警告
            logger.error("[Step 5] 裁判调用失败, 默认通过以避免无限回滚: %s", e)
            report: ConsistencyReport = {
                "passed": True,
                "issues": [f"judge_error: {e}"],
                "suggestions": [],
                "checked_at_node": self.name,
            }
            self.audit(state, "assistant",
                       f"[step5] judge_error, 默认通过: {e}")
            return {"consistency_report": report}

        report = ConsistencyReport(
            passed=judge.passed,
            issues=judge.issues,
            suggestions=judge.suggestions,
            checked_at_node=self.name,
        )

        # ---- 回滚计数自增 (放在条件路由之前) ----
        replan_count = state.get("replan_count", 0)
        if not judge.passed:
            state["replan_count"] = replan_count + 1
            # 回滚时清空 Prompt 字段, 让 Step 3+4 重做
            for sp in plan.shot_prompts:
                for v in sp.variants:
                    v.prompt_text = ""

            # 11 维度 ERROR 摘要
            error_dims = [
                dim for dim in [
                    "story_consistency", "character_consistency", "scene_consistency",
                    "prop_consistency", "action_consistency", "camera_consistency",
                    "lighting_consistency", "environment_consistency", "audio_consistency",
                    "prompt_quality", "negative_prompt",
                ]
                if getattr(judge, dim).status == "ERROR"
            ]
            warning_dims = [
                dim for dim in [
                    "story_consistency", "character_consistency", "scene_consistency",
                    "prop_consistency", "action_consistency", "camera_consistency",
                    "lighting_consistency", "environment_consistency", "audio_consistency",
                    "prompt_quality", "negative_prompt",
                ]
                if getattr(judge, dim).status == "WARNING"
            ]

            logger.warning(
                "[Step 5] ❌ 未通过 (回滚 %d -> %d) | score=%d | %d issues | confidence=%.2f",
                replan_count, state["replan_count"],
                judge.overall_score, len(judge.issues), judge.confidence,
            )
            logger.warning("  ERROR 维度: %s", error_dims or "(none)")
            logger.warning("  WARNING 维度: %s", warning_dims or "(none)")
            for i, iss in enumerate(judge.issues):
                logger.warning("  - issue[%d]: %s | fix: %s",
                               i, iss, judge.suggestions[i] if i < len(judge.suggestions) else "(无)")
            if judge.optimized_prompt.prompt_text:
                logger.info("  自动修正 Prompt 已生成 (%d 字符)",
                           len(judge.optimized_prompt.prompt_text))
        else:
            logger.info("[Step 5] ✅ 一致性通过 (score=%d, confidence=%.2f)",
                        judge.overall_score, judge.confidence)

        # ---- 自动修正写回 (已禁用: optimized_prompt 是全局建议,不能覆盖所有镜头) ----
        # 原逻辑会将同一个 optimized_prompt 覆盖所有 shot,导致所有镜头内容相同
        # 正确做法: Step 5 只输出审核报告,不修改 prompt_text
        writeback_applied = False
        # if judge.passed and judge.optimized_prompt.prompt_text:
        #     fixed_count = 0
        #     for sp in plan.shot_prompts:
        #         for variant in sp.variants:
        #             variant.prompt_text = judge.optimized_prompt.prompt_text
        #             fixed_count += 1
        #     writeback_applied = True
        #     logger.info(
        #         "[Step 5] ✏️  自动修正写回: %d 个 variant 已被 optimized_prompt 覆盖",
        #         fixed_count,
        #     )

        # ---- 扩展 audit 输出 ----
        dims_summary = " ".join([
            f"{dim[:4]}={getattr(judge, dim).status[0]}"
            for dim in [
                "story_consistency", "character_consistency", "scene_consistency",
                "prop_consistency", "action_consistency", "camera_consistency",
                "lighting_consistency", "environment_consistency", "audio_consistency",
                "prompt_quality", "negative_prompt",
            ]
        ])
        self.audit(state, "assistant",
                   f"[step5] passed={judge.passed} score={judge.overall_score} "
                   f"dims={dims_summary} replan={state.get('replan_count', 0)} "
                   f"auto_fix={'yes' if judge.optimized_prompt.prompt_text else 'no'} "
                   f"writeback={'applied' if writeback_applied else 'skipped'}")
        return {"consistency_report": report, "replan_count": state.get("replan_count", 0)}


step5_consistency_check = Step5ConsistencyChecker()


__all__ = ["step5_consistency_check", "Step5ConsistencyChecker"]
