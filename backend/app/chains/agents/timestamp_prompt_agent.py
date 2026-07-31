"""时间戳 Prompt Agent：生成带时间戳节奏的视频 Prompt。

移植自 Pipeline Step4_Writer，使用 @角色名 引用 + 时间戳格式。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from app.chains.agents.base import AgentBase, _extract_json_from_text


class TimestampPromptResult(BaseModel):
    """时间戳 Prompt 结果。"""
    prompt_text: str = Field(default="", description="时间戳 Prompt")
    negative_prompt: str = Field(default="", description="负面提示词")


_TIMESTAMP_SYSTEM = """\
# Role

你是一位 AI 视频 Prompt 专家，熟悉：即梦 / 可灵 / Veo / Runway / Pika / PixVerse / 海螺 / Sora 等。

你的职责：
**根据镜头信息和 Beat 序列生成可以直接用于 AI 视频模型的时间戳 Prompt。**

硬禁令：
- ❌ 禁止修改剧情
- ❌ 禁止修改 Beat
- ❌ 禁止新增人物

# 输出格式

[0-Xs] 起始状态：@角色名 + 动作/表情 + 环境 + 光线 + 摄影参数(景别/焦段/机位/构图)
[X-Ys] Beat1：@角色名 + 动作/微表情/眼神 + 摄影参数(运镜方式)
[Y-Zs] Beat2：@角色名 + 动作/肢体 + 环境变化
...
[末段] 结束画面：@角色名 + 最终姿态 + 静止构图

镜头节奏：快/慢/停顿/留白
摄影总结：景别/运镜/光色/构图
负面：人物变形/穿模/物理错误

**重要**：@角色名 是角色资产引用，**不要**在 prompt 中重复描述角色的外貌（年龄/身高/脸型/肤色/发型/服装等）。

# 摄影参数要求

每个时间段必须包含（丰富版）：
- 景别：wide/medium/close-up/extreme-close-up
- 焦段：24mm/35mm/50mm/85mm/135mm
- 机位：平视/低角度仰拍/高角度俯拍
- 构图：三分法/居中/对角线
- 运镜：static/dolly-in/pan-left/tilt-up/...
- 运镜：static/dolly-in/pan-left/tilt-up/handheld/tracking/orbital/crane...
- 光线：cinematic lighting / 侧逆光 / 顶光 / 具体光源方向
- 光线：cinematic lighting / 侧逆光 / 顶光 / 刺眼光束 / 灰尘中的光柱

# 电影艺术风格动作摄影词汇

鼓励在 Prompt 中使用以下摄影风格术语：
- **手持能量**：轻微晃动，临场感
- **快速平移**：快速水平跟随主体的摇镜
- **轨道环绕**：弧线轨道围绕主体旋转
- **头顶俯瞰**：鸟瞰视角
- **侧面剪影**：长焦侧面轮廓
- **激进特写**：极端近景，强调微表情
- **长焦压缩**：空间扁平化，主体和背景压缩在一起
- **极端低角度**：贴地仰拍，放大力量
- **宽广负空间**：主体很小，环境广阔
- **强视差**：前景和背景以不同速度移动

# 元素能量效果（VFX 风格指导）

如果镜头包含动作/战斗/冲击场景，可在 Prompt 中适当加入元素能量效果：
- **空气爆发**：旋转和飞踢周围的空气冲击波
- **尘土碎片**：跺脚或撞击时升起的尘土和石块
- **地面涟漪**：滑行或扫腿时的水状地面波纹
- **火焰轨迹**：爆发打击周围的火焰状能量轨迹
- **热扭曲**：高强度运动周围的热浪变形
- **元素漩涡**：高潮时周围元素的旋转汇聚

**原则**：元素效果应感觉电影化而非超级英雄式。它们是对物理动作的强调，而非魔法或超能力。

# 环境极简原则

- 环境描述只保留氛围所需的最小元素（如：高耸石柱、飘浮香烟、光束、微弱尘土）
- **不要让画面过于拥挤**——留出负空间让主体突显
- 环境是背景，不是主角

# Prompt 生成规则（硬约束）

每个 Prompt **必须**描述：
1. **主体是谁**（用 @角色名）
2. **主体在哪里**
3. **主体在干什么**
4. **摄影机如何拍**
5. **摄影机什么时候运动**
6. **人物什么时候动作**（Beat-aligned）
7. **环境什么时候变化**
8. **什么时候结束镜头**

# Prompt 要求（红线）

- ❌ 禁止文学描写（比喻/拟人/排比/借代）
- ❌ **严禁抽象情感词**（以下词汇绝对不能出现）：
  - 绝望 / 决绝 / 希望 / 挣扎 / 矛盾 / 纠结
  - 孤独 / 悲伤 / 痛苦 / 压抑 / 恐惧 / 焦虑 / 愤怒
  - 交织 / 流露 / 透出 / 充满（用于描述情感时）
- ✅ 情绪只能通过**可见的物理动作**表达：
  - 错误："眼神中交织着绝望与决绝"
  - 正确："眉头紧锁，嘴唇抿成一条线，手指微微发颤"
- ✅ 眼神/表情只能描述**可见的肌肉动作**

# 角色引用规则（严格执行）

@角色名 是角色资产图片的引用。
1. **@角色名 = 角色资产引用**：不需要在 prompt 中重复角色的外貌描述
2. **Prompt 只描述**：动作 / 表情 / 肢体语言 / 位置 / 与环境的互动
3. **禁止重复外貌**：不能写 "@陆沉, 20岁, 178cm, 窄脸..." ❌

正确示例：
- ❌ "@陆沉, 年龄约20岁, 身形清瘦, 面部棱角分明的窄脸..."
- ✅ "@陆沉 坐在昏暗出租屋中央的旧木椅上, 低头看左手捏着的揉皱诊断证明"

# 物理真实感要求

- ✅ 真实重力感：脚步有踩地反馈
- ✅ 真实惯性感：快速动作后有惯性延续
- ✅ 真实重量感：物体拿取/放下有重量反馈
- ✅ 真实速度感：快速动作有运动模糊
- ❌ 禁止：反物理动作、漂浮感、失重感、机械感

# 负面提示词（必须包含）

人物：变形、多指、少指、穿模、肢体扭曲、面部崩坏
物理：失重感、漂浮感、反物理动作、机械感
画面：AI感、CG感、游戏感、过度锐化、过度美颜
质感：塑料皮肤、蜡像感
干扰：文字字幕、水印、LOGO
干扰：文字字幕、水印、LOGO、额外角色、标志
镜头：镜头漂移、背景跳变
镜头：镜头漂移、背景跳变、画面抖动
动作：静态站姿、舞蹈式浮夸、缺乏重量感、机械重复

# 输出 JSON

{"prompt_text": "...", "negative_prompt": "..."}

- prompt_text 长度 >= 50 字符
- negative_prompt 必须填写
- 时间戳格式：[0-2s]（整数秒），[2.5-4s]（0.5 步进）
"""

_TIMESTAMP_TEMPLATE = """\
## 目标模型
{target_model}

## 模型风格指令
{style_guide}

## 演员表引用
本镜头角色：{character_names_at}
✅ 使用 @角色名 引用即可，**不要重复描述外貌**
✅ 只描述：动作 / 表情 / 位置 / 与环境的互动

## 镜头上下文
剧本摘录：{script_excerpt}
镜头标题：{title}
景别：{camera_shot}
机位：{angle}
运镜：{movement}
氛围：{atmosphere}
时长：{duration}秒

## Beat 序列
{beat_sequence}

## 声音设计
{sound_design}

## 主体分析
{subject_analysis}

## 已确认实体上下文
角色：{character_context}
场景：{scene_context}
道具：{prop_context}
服装：{costume_context}

## 相邻镜头承接
上一镜头：{previous_shot_title} - {previous_shot_end_state}
下一镜头：{next_shot_title} - {next_shot_start_goal}

## 导演指令
{director_command_summary}

## Beat 强度递进参考
{intensity_guide}

## 摄影机运动参考
本镜头可用摄影风格：手持能量、快速平移、轨道环绕、头顶俯瞰、侧面剪影、激进特写、长焦压缩、极端低角度、宽广负空间、强视差

请输出时间戳 Prompt JSON: prompt_text + negative_prompt。
"""


class TimestampPromptAgent(AgentBase[TimestampPromptResult]):
    """时间戳 Prompt Agent。"""

    @property
    def prompt_template(self) -> PromptTemplate:
        return PromptTemplate(
            input_variables=[
                "target_model", "style_guide", "character_names_at",
                "script_excerpt", "title", "camera_shot", "angle", "movement",
                "atmosphere", "duration", "beat_sequence", "sound_design",
                "subject_analysis", "character_context", "scene_context",
                "prop_context", "costume_context",
                "previous_shot_title", "previous_shot_end_state",
                "next_shot_title", "next_shot_start_goal",
                "director_command_summary", "intensity_guide",
            ],
            template=_TIMESTAMP_TEMPLATE,
        )

    @property
    def output_model(self) -> type[TimestampPromptResult]:
        return TimestampPromptResult

    @property
    def system_prompt(self) -> str:
        return _TIMESTAMP_SYSTEM

    def extract(self, **kwargs: Any) -> TimestampPromptResult:
        inp = self._prepare_input(kwargs)
        raw = self.run(**inp)
        return self.format_output(raw)

    async def aextract(self, **kwargs: Any) -> TimestampPromptResult:
        inp = self._prepare_input(kwargs)
        raw = await self.arun(**inp)
        return self.format_output(raw)

    def format_output(self, raw: str) -> TimestampPromptResult:
        json_str = _extract_json_from_text(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return TimestampPromptResult(prompt_text=raw.strip())
        return TimestampPromptResult(
            prompt_text=str(data.get("prompt_text", "")).strip(),
            negative_prompt=str(data.get("negative_prompt", "")).strip(),
        )

    @staticmethod
    def _prepare_input(kwargs: dict[str, Any]) -> dict[str, Any]:
        defaults = {
            "target_model": "通用", "style_guide": "使用通用高质量视频 Prompt 风格",
            "character_names_at": "", "script_excerpt": "", "title": "",
            "camera_shot": "", "angle": "", "movement": "",
            "atmosphere": "", "duration": 0, "beat_sequence": "",
            "sound_design": "", "subject_analysis": "",
            "character_context": "", "scene_context": "",
            "prop_context": "", "costume_context": "",
            "previous_shot_title": "", "previous_shot_end_state": "",
            "next_shot_title": "", "next_shot_start_goal": "",
            "director_command_summary": "",
        }
        for key, default in defaults.items():
            if key not in kwargs or kwargs[key] is None:
                kwargs[key] = default
        return kwargs


# 模型风格指令
MODEL_STYLE_GUIDE: dict[str, str] = {
    "kling": (
        "Kling 1.6 风格：强调物理真实感，运镜用中文描述（推/拉/摇/移/跟/升/降）；"
        "prompt_text 简洁直接 + 摄影指令（如 cinematic, dolly in）；"
        "negative_prompt: '变形, 穿模, 失重, 僵硬'"
    ),
    "jimeng": (
        "即梦（字节）风格：强调画面美感，色彩/光影/构图；"
        "prompt_text 简洁，长度（80-150 字）为宜，避免过于技术化；"
        "negative_prompt: '变形, 模糊, 低质量'"
    ),
    "veo": "Veo 风格：英文优先，简洁直接，强调真实物理感",
    "runway": "Runway 风格：强调运动描述和镜头运动，时间节奏明确",
    "pixverse": "PixVerse 风格：简洁描述优先，避免过长 prompt",
}


__all__ = ["TimestampPromptAgent", "TimestampPromptResult", "MODEL_STYLE_GUIDE"]
