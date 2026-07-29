"""Step 4 Agent —— Prompt Writer (核心生成节点)。

输入: state["story_analysis"] + state["storyboard"] + state["prompt_plan"]
输出: 更新 state["prompt_plan"] (填充每个 PromptVariant.prompt_text)
      + 在 output_dir 写一份 Excel 交付物
"""

from __future__ import annotations
import pathlib

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ..graph.state import GraphState
from ..schemas import PromptVariant
from ..schemas.enums import TargetModel
from ..utils import export_prompts_to_excel, get_llm, get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


# ---- 5 模型的 Prompt 风格指令 (Step 6 的雏形, Step 4 阶段使用以提高质量) ----
MODEL_STYLE_GUIDE: dict[str, str] = {
    TargetModel.KLING.value:
        "Kling 1.6 ??: ?????????, ?????????; "
        "prompt_text ???? + ?????? (? cinematic, dolly in); "
        "negative_prompt: '??, ???, ??, ??'",

    TargetModel.JIMENG.value:
        "?? (??) ??: ??????????, ????/??/??; "
        "prompt_text ???, ?? (80-150 ?) ??????; "
        "negative_prompt: '??, ??, ???'",
}


_WRITER_SYSTEM = """# Role

你是一位 AI 视频 Prompt 专家, 熟悉: 即梦 / 可灵 / Veo / Runway / Pika / PixVerse / 海螺 / Sora 等。

你的职责:
**根据 PromptPlan 生成可以直接用于 AI 视频模型的视频 Prompt。**

硬禁令:
- ❌ 禁止修改剧情
- ❌ 禁止修改 Beat
- ❌ 禁止新增人物

# 输入

PromptPlan JSON (含 Step 3 的 subject_analysis / beats / sound_design / prompt_strategy)
+ 演员表 (character_sheets): 每个角色的完整视觉描述

# 工作目标

对每一个镜头, 输出 **1 个增强版时间戳 Prompt**。

# 输出格式

```
[0-Xs] 起始状态: @角色名 + 动作/表情 + 环境 + 光线 + 摄影参数(景别/焦段/机位/构图)
[X-Ys] Beat1: @角色名 + 动作/微表情/眼神 + 摄影参数(运镜方式)
[Y-Zs] Beat2: @角色名 + 动作/肢体 + 环境变化
...
[末段] 结束画面: @角色名 + 最终姿态 + 静止构图

镜头节奏: 快/慢/停顿/留白
摄影总结: 景别/运镜/光色/构图
负面: 人物变形/穿模/物理错误
```

**重要**: @角色名 是角色资产引用，**不要**在 prompt 中重复描述角色的外貌（年龄/身高/脸型/肤色/发型/服装等）。

# 摄影参数要求 (融合专业调度)

每个时间段必须包含:
- 景别: wide/medium/close-up/extreme-close-up
- 焦段: 24mm/35mm/50mm/85mm/135mm
- 机位: 平视/低角度仰拍/高角度俯拍
- 构图: 三分法/居中/对角线
- 运镜: static/dolly-in/pan-left/tilt-up/...
- 光线: cinematic lighting / 侧逆光 / 顶光 / 具体光源方向

# 叙事要求 (融合流畅性)

- 时间段之间保持叙事连贯性，动作自然过渡
- 环境描写融入动作描述中，不单独割裂
- 声音设计与画面节奏同步

# Prompt 生成规则 (硬约束)

每个 Prompt **必须**描述:
1. **主体是谁** (用 @角色名 或完整描述)
2. **主体在哪里** (引用 scenes[].location)
3. **主体在干什么** (action)
4. **摄影机如何拍** (camera + framing)
5. **摄影机什么时候运动** (camera timing)
6. **人物什么时候动作** (Beat-aligned)
7. **环境什么时候变化** (env_change)
8. **声音什么时候出现** (sound)
9. **什么时候结束镜头** (end frame)

# Prompt 要求 (红线)

- ❌ 禁止文学描写 (比喻/拟人/排比/借代)
- ❌ **严禁抽象情感词** (以下词汇绝对不能出现):
  - 绝望 / 决绝 / 希望 / 挣扎 / 矛盾 / 纠结
  - 孤独 / 悲伤 / 痛苦 / 压抑 / 恐惧 / 焦虑 / 愤怒
  - 交织 / 流露 / 透出 / 充满 (用于描述情感时)
  - 最后的 / 内心的 / 深处的 (用于修饰情感时)
- ✅ 情绪只能通过**可见的物理动作**表达:
  - 错误: “眼神中交织着绝望与决绝”
  - 正确: “眉头紧锁, 嘴唇抿成一条线, 手指微微发颤”
  - 错误: “他内心充满挣扎”
  - 正确: “他反复握紧又松开拳头, 喉结上下滚动”
- ✅ 眼神/表情只能描述**可见的肌肉动作**, 不能描述“情绪状态”:
  - 错误: “眼神中透出最后的挣扎”
  - 正确: “瞳孔微微收缩, 眼睑眯起, 目光固定在某处”

# 人物一致性 (Step 5 会审计)

保持: 年龄 / 服装 / 发型 / 五官 / 道具 / 动作习惯 / 惯用手 / 饰品 全部一致。

**角色引用规则 (严格执行)**:

@角色名 是**角色资产图片的引用**（类似 libtv 的 @asset），视频工具会自动查找演员表中的形象描述。

1. **@角色名 = 角色资产引用**: 不需要在 prompt 中重复角色的外貌描述（年龄/身高/脸型/肤色/发型/服装等）
2. **Prompt 只描述**: 动作 / 表情 / 肢体语言 / 位置 / 与环境的互动
3. **禁止重复外貌**: 不能写 "@陆沉, 20岁, 178cm, 窄脸, 苍白肤色..." ❌

**正确示例**:
- ❌ 错误: "@陆沉, 年龄约20岁, 身高约178cm, 身形清瘦, 面部棱角分明的窄脸, 肤色苍白, 黑色短发..."
- ✅ 正确: "@陆沉 坐在昏暗出租屋中央的旧木椅上, 低头看左手捏着的揉皱诊断证明"
- ✅ 正确: "@陆沉 右手夹着劣质香烟抬到嘴边深吸一口, 烟头火光短暂照亮他的侧脸"

**原因**: @陆沉 已经引用了角色资产图片，视频工具知道陆沉长什么样。重复描述会浪费 token 且可能导致冲突。

# 场景一致性

保持: 天气 / 时间 / 家具 / 建筑 / 光线 / 背景 全部一致。

# AI 视频优化规则

- 同一剧情 Beat 的连续动作 → **不要切镜**
- 同一情绪的连续动作 → **不要切镜**
- Prompt 必须符合: 真实摄影 / 真实人体动作 / 真实物理规律

# 物理真实感要求 (必须遵守)

人物动作必须有**真实物理感**:
- ✅ 真实重力感: 脚步有踩地反馈, 不能漂浮
- ✅ 真实惯性感: 快速动作后有惯性延续, 衣物随动作摆动
- ✅ 真实重量感: 物体拿取/放下有重量反馈
- ✅ 真实速度感: 快速动作有运动模糊和速度拖影
- ✅ 真实发力感: 肌肉紧张、身体重心变化、呼吸配合
- ❌ 禁止: 反物理动作、漂浮感、失重感、机械感、僵硬感

**动作编排参考词汇** (根据场景选用):
- 近战: 拆招、格挡、闪避、踢腿、错身、拧腰、沉肩、翻腕
- 轻功: 飞掠、腾空、落地、借力、旋身、点地
- 暗器: 翻腕、掏出、甩手、掷出、破空
- 表情: 眼神收紧、眉头微蹙、嘴角含笑、瞳孔收缩
- 日常: 抬眼、侧头、握拳、松手、转身、蹲下

# 风格参考与导演语言

如果 PromptPlan 中有导演风格指示, 在 prompt 中明确引用:
- 格式: "风格参考: [导演名] 的 [特点]"
- 示例: "风格参考: 徐克武侠电影的镜头调度与动作节奏"
- 示例: "色调参考: 《倩女幽魂》的自然山林质感"
- 示例: "轻功效果: 参考《笑傲江湖》的实拍威亚飞掠感"

# 负面提示词增强 (negative_prompt)

必须包含以下禁止项:
- 人物: 变形、多指、少指、穿模、肢体扭曲、面部崩坏
- 物理: 失重感、漂浮感、反物理动作、机械感、僵硬感
- 画面: AI感、CG感、游戏感、动画感、过度锐化、过度美颜
- 质感: 塑料皮肤、蜡像感、假发感、廉价布料
- 干扰: 文字字幕、水印、LOGO、边框、分屏
- 镜头: 镜头漂移、背景跳变、穿帮、空间混乱
- 特效: 廉价特效、光污染、色彩过饱和、粒子过多

# 输出 JSON (Pydantic 校验)

{
  "prompt_text": "...",
  "negative_prompt": "人物变形, 多指, 少指, 穿模, 肢体扭曲, 面部崩坏, 失重感, 漂浮感, 反物理动作, 机械感, 僵硬感, AI感, CG感, 游戏感, 过度锐化, 过度美颜, 塑料皮肤, 蜡像感, 文字字幕, 水印, LOGO, 镜头漂移, 背景跳变, 廉价特效, 光污染"
}

- prompt_text 长度 >= 50 字符
- negative_prompt 必须填写
- 时间区间严格用 beats 中的 start_time/end_time
- 每个时间槽都必须有: 主体 + 动作 + 摄影 + 环境 至少 1 项
- 时间戳格式: `[0-2s]` (整数秒), `[2.5-4s]` (带小数, 0.5 步进)
"""


class Step4Writer(BaseAgent):
    name = "step4_writer"
    system_prompt = _WRITER_SYSTEM
    temperature = 0.75

    def __call__(self, state: GraphState) -> dict[str, Any]:
        analysis = state.get("story_analysis")
        storyboard = state.get("storyboard")
        plan = state.get("prompt_plan")
        if analysis is None or storyboard is None or plan is None:
            logger.error("[Step 4] 上游产物缺失, 无法继续")
            return {}
        logger.info("[Step 4] 开始 Prompt 撰写 (%d 变体)", sum(len(sp.variants) for sp in plan.shot_prompts))

        shot_map = {s.shot_id: s for s in storyboard.shots}
        char_map = {c.character_id: c for c in analysis.characters}

        # ---- 构建演员表: {角色名: character_sheet文本} ----
        # 优先使用全局演员表 (cast_data), 否则使用本章 analysis
        cast_data = state.get("cast_data") or {}
        character_sheet_map: dict[str, str] = {}
        for c in analysis.characters:
            # 优先从全局演员表获取
            if c.name in cast_data:
                character_sheet_map[c.name] = (
                    cast_data[c.name].get("character_sheet", "")
                    or cast_data[c.name].get("base_appearance", "")
                    or c.character_sheet
                    or c.visual_anchor
                    or c.appearance
                    or ""
                )
            else:
                character_sheet_map[c.name] = c.character_sheet or c.visual_anchor or c.appearance or ""

        # ---- 跟踪角色首次出现 (用于决定是否完整描述) ----
        introduced_characters: set[str] = set()

        llm = get_llm(temperature=self.temperature)

        updated_count = 0
        failed: list[tuple[str, str, str]] = []  # (shot_id, model, reason)

        for sp in plan.shot_prompts:
            shot = shot_map.get(sp.shot_id)
            if not shot:
                logger.warning("[Step 4] shot_id=%s 在 Storyboard 中找不到, 跳过", sp.shot_id)
                continue

            # 收集该镜头的关键上下文
            shot_ctx = {
                "shot_id": shot.shot_id,
                "scene_id": shot.scene_id,
                "duration_sec": shot.duration_sec,
                "framing": shot.framing.value,
                "camera": shot.camera.value,
                "description": shot.description,
                "characters_in_shot": [
                    {
                        "id": cid,
                        "name": char_map[cid].name if cid in char_map else cid,
                        "character_sheet": character_sheet_map.get(
                            char_map[cid].name if cid in char_map else cid, ""
                        ),
                        "already_introduced": (
                            char_map[cid].name if cid in char_map else cid
                        ) in introduced_characters,
                        "reference_image_url": getattr(char_map.get(cid), "reference_image_url", "") or "",
                    }
                    for cid in shot.characters_in_shot
                ],
                "dialogue": [d.model_dump() for d in shot.dialogue],
                "visual_style": (shot.visual_style_override or analysis.visual_style).value,
                # ---- Step 3 Beat 序列 (时间戳版必用) ----
                "beats": getattr(sp, "beats", []) or [],
                "props_in_shot": shot.props_in_shot or [],
                "sound_design": getattr(sp, "sound_design", {}) or {},
            }

            for variant in sp.variants:
                # 跳过已填充的 (回滚场景下, Step 3 会清空让 Step 4 重写)
                if variant.prompt_text:
                    continue

                style_guide = MODEL_STYLE_GUIDE.get(variant.target_model.value, "")

                # 时间戳节奏的额外提示
                beat_count = len(shot_ctx.get("beats") or [])
                timing_hint = (
                    f"\n\n## 时间戳节奏要求\n"
                    f"- 本镜头有 {beat_count} 个 Beat, duration_sec={shot.duration_sec}\n"
                    f"- 必须按 beats 生成时间戳节奏: [0-2s] / [2-3.5s] / [3.5-5s] ...\n"
                    f"- 每个时间槽: 主体 + 动作 + 摄影 + 环境 至少 1 项\n"
                    f"- 时间区间严格用 beats 中的 start_time/end_time"
                    if beat_count > 0 else
                    "\n\n## 时间戳节奏提示\n"
                    "- 本镜头无 Beat 数据, 按镜头时长均分时间戳节奏"
                )

                # 演员表引用提示: 所有角色都用 @引用, 不重复外貌描述
                chars_in_shot = [c["name"] for c in shot_ctx["characters_in_shot"]]
                cast_hint = ""
                if chars_in_shot:
                    cast_hint += f"\n\n## 演员表引用\n"
                    cast_hint += f"- 本镜头角色: {', '.join(f'@{name}' for name in chars_in_shot)}\n"
                    cast_hint += f"- ✅ 使用 @角色名 引用即可, **不要重复描述外貌**\n"
                    cast_hint += f"- ✅ 只描述: 动作 / 表情 / 位置 / 与环境的互动"

                user_prompt = (
                    f"## 目标模型\n{variant.target_model.value}\n\n"
                    f"## 模型风格指令\n{style_guide or '(使用通用高质量视频 Prompt 风格)'}\n\n"
                    f"## 镜头上下文\n```json\n{_safe_json(shot_ctx)}\n```\n\n"
                    f"## 已有备注\n{variant.notes or '(无)'}\n"
                    f"{cast_hint}"
                    f"{timing_hint}\n\n"
                    "请输出增强版时间戳 Prompt JSON: prompt_text + negative_prompt。"
                )

                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=user_prompt),
                ]
                try:
                    resp = llm.invoke(messages)
                    raw = resp.content if isinstance(resp.content, str) else str(resp.content)

                    # 检测是否因 max_tokens 截断
                    finish_reason = getattr(resp, "response_metadata", {}).get("finish_reason", "")
                    if finish_reason == "length":
                        logger.warning(
                            "[Step 4] shot=%s model=%s ⚠️ LLM 输出被 max_tokens 截断 (finish_reason=length), "
                            "建议增大 LLM_MAX_TOKENS 环境变量",
                            sp.shot_id, variant.target_model.value,
                        )

                    from ..utils import safe_parse_json
                    data = safe_parse_json(raw)

                    # 解析输出 (只有 prompt_text + negative_prompt)
                    variant.prompt_text = data.get("prompt_text", "").strip()
                    variant.negative_prompt = data.get("negative_prompt", "").strip()

                    # 兆底: 如果 prompt_text 为空, 尝试从 version_b 字段读取 (兼容旧格式)
                    if not variant.prompt_text:
                        variant.prompt_text = data.get("version_b", "").strip()

                    updated_count += 1

                    # 标记本镜头角色已介绍
                    for c in shot_ctx["characters_in_shot"]:
                        introduced_characters.add(c["name"])

                    # 后处理: 检测抽象情感词并告警
                    _abstract_words = [
                        "绝望", "决绝", "希望", "挣扎", "矛盾", "纠结",
                        "孤独", "悲伤", "痛苦", "压抑", "恐惧", "焦虑", "愤怒",
                        "交织", "流露", "透出", "充满",
                    ]
                    found = [w for w in _abstract_words if w in variant.prompt_text]
                    if found:
                        logger.warning(
                            "[Step 4] shot=%s model=%s prompt_text 含抽象情感词: %s",
                            sp.shot_id, variant.target_model.value, ", ".join(found),
                        )

                    # 后处理: 检测英文裸名 (应使用 @角色名 引用)
                    import re as _re
                    _char_names = list(character_sheet_map.keys())
                    _en_patterns = []
                    for name in _char_names:
                        # 简单拼音映射 (可扩展)
                        _pinyin_map = {
                            "陆沉": r"\b(Lu Chen|LuChen)\b",
                            "赵无极": r"\b(Zhao Wuji|ZhaoWuji)\b",
                            "秘书": r"\b(Secretary|secretary)\b",
                            "高挑秘书": r"\b(tall slender secretary|tall secretary)\b",
                        }
                        if name in _pinyin_map:
                            _en_patterns.append((name, _pinyin_map[name]))
                    bare_names = []
                    for cn_name, pattern in _en_patterns:
                        if _re.search(pattern, variant.prompt_text, _re.IGNORECASE):
                            bare_names.append(cn_name)
                    if bare_names:
                        logger.warning(
                            "[Step 4] shot=%s model=%s ⚠️ 含英文裸名 (应使用 @引用): %s",
                            sp.shot_id, variant.target_model.value, ", ".join(bare_names),
                        )
                        # 自动替换: 将英文裸名替换为 @中文名
                        for cn_name, pattern in _en_patterns:
                            variant.prompt_text = _re.sub(
                                pattern, f"@{cn_name}", variant.prompt_text, flags=_re.IGNORECASE
                            )
                        logger.info(
                            "[Step 4] shot=%s model=%s ✏️  已自动替换英文裸名为 @引用",
                            sp.shot_id, variant.target_model.value,
                        )

                    logger.info(
                        "[Step 4] shot=%s model=%s ✅ %d 字符",
                        sp.shot_id, variant.target_model.value,
                        len(variant.prompt_text),
                    )
                except Exception as e:  # noqa: BLE001
                    failed.append((sp.shot_id, variant.target_model.value, str(e)[:200]))
                    logger.warning("[Step 4] shot=%s model=%s ❌ %s",
                                   sp.shot_id, variant.target_model.value, e)

        # ---- Step 4 不再导出 Excel, 由 main.py 统一导出最终版本 ----

        audit_msg = (
            f"[step4] 撰写完成: {updated_count}/{sum(len(sp.variants) for sp in plan.shot_prompts)} 成功, "
            f"{len(failed)} 失败"
        )
        if failed:
            audit_msg += f"\n失败明细:\n" + "\n".join(f"  - {s}/{m}: {r}" for s, m, r in failed[:10])
        self.audit(state, "assistant", audit_msg)
        logger.info("[Step 4] ✅ %d/%d 变体已填充", updated_count,
                    sum(len(sp.variants) for sp in plan.shot_prompts))
        # ?? Excel
        output_dir = state.get("output_dir", "./output")
        try:
            export_prompts_to_excel(
                storyboard=storyboard,
                prompt_plan=plan,
                output_dir=output_dir,
                story_title=analysis.title,
                story_analysis=analysis,
                cast_data=cast_data,
            )
        except Exception as e:
            logger.warning("[Step 4] Excel export failed: %s", e)

        return {"prompt_plan": plan}


step4_write_prompts = Step4Writer()


def _safe_json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)


__all__ = ["step4_write_prompts", "Step4Writer"]