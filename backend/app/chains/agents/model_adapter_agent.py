"""模型适配 Agent：根据目标模型优化 Prompt 格式。

移植自 Pipeline Step6_Adapter，适配 Jellyfish 数据。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class ModelAdaptResult(BaseModel):
    """模型适配结果。"""
    prompt_text: str = Field(default="", description="适配后的 Prompt")
    negative_prompt: str = Field(default="", description="负面提示词")
    target_model: str = Field(default="", description="目标模型")
    notes: str = Field(default="", description="适配说明")


# 运镜中英文映射（Kling 用中文）
_CAMERA_ZH = {
    "dolly_in": "推镜头", "dolly_out": "拉镜头",
    "pan_left": "左平移", "pan_right": "右平移",
    "tilt_up": "上摇", "tilt_down": "下摇",
    "track_left": "左跟拍", "track_right": "右跟拍",
    "crane_up": "升摇", "crane_down": "降摇",
    "zoom_in": "推镜头", "zoom_out": "拉镜头",
    "handheld": "手持", "drone_aerial": "航拍",
    "static": "固定机位",
    "STATIC": "固定机位", "DOLLY_IN": "推镜头", "DOLLY_OUT": "拉镜头",
    "PAN": "平移", "TRACK": "跟拍", "CRANE": "摇臂",
}


def _optimize_kling(text: str, camera: str = "") -> str:
    """Kling：补充中文运镜，强化物理真实感。"""
    cam_zh = _CAMERA_ZH.get(camera, "固定机位")
    if cam_zh not in text:
        return f"{text} ({cam_zh} cinematic)"
    return text


def _optimize_jimeng(text: str, min_len: int = 80) -> str:
    """即梦：确保长度 >= 80 字符，补充通用画面描述。"""
    if len(text) >= min_len:
        return text
    padding = "，电影级光影，细腻皮肤质感，真实物理运动，自然光线过渡，背景虚化层次分明"
    return f"{text}{padding}"


def _optimize_veo(text: str) -> str:
    """Veo：英文优先，简洁直接。"""
    return text


def _optimize_runway(text: str) -> str:
    """Runway：强调运动描述和镜头运动。"""
    return text


def _optimize_pixverse(text: str) -> str:
    """PixVerse：简洁描述优先。"""
    return text

def _optimize_sora(text: str) -> str:
    """Sora??????????????????????"""
    return text + ", photorealistic, natural physics, coherent motion, cinematic"


def _optimize_hailuo(text: str) -> str:
    """Hailuo??????????????????"""
    if len(text) < 80:
        return text + "????????????????????"
    return text + "????"


_OPTIMIZERS = {
    "kling": _optimize_kling,
    "jimeng": _optimize_jimeng,
    "veo": _optimize_veo,
    "runway": _optimize_runway,
    "pixverse": _optimize_pixverse,
    "sora": _optimize_sora,
    "hailuo": _optimize_hailuo,
}


# 通用负面提示词
_DEFAULT_NEGATIVE = (
    "人物变形, 多指, 少指, 穿模, 肢体扭曲, 面部崩坏, "
    "失重感, 漂浮感, 反物理动作, 机械感, 僵硬感, "
    "AI感, CG感, 游戏感, 过度锐化, 过度美颜, "
    "塑料皮肤, 蜡像感, 文字字幕, 水印, LOGO, "
    "镜头漂移, 背景跳变, 廉价特效, 光污染"
)


def adapt_prompt_for_model(
    prompt_text: str,
    *,
    target_model: str,
    camera: str = "",
    negative_prompt: str = "",
) -> ModelAdaptResult:
    """根据目标模型适配 Prompt。

    这是纯函数，不需要 LLM 调用。
    """
    model_key = target_model.lower().strip()
    optimizer = _OPTIMIZERS.get(model_key)

    if optimizer:
        if model_key == "kling":
            adapted = optimizer(prompt_text, camera)
        else:
            adapted = optimizer(prompt_text)
    else:
        adapted = prompt_text

    neg = negative_prompt.strip() if negative_prompt else _DEFAULT_NEGATIVE

    return ModelAdaptResult(
        prompt_text=adapted,
        negative_prompt=neg,
        target_model=model_key,
        notes=f"已适配 {model_key}" if optimizer else f"未知模型 {model_key}，使用通用格式",
    )


class ModelAdapterAgent:
    """模型适配 Agent（不需要 LLM，纯规则优化）。"""

    def extract(
        self,
        *,
        prompt_text: str,
        target_model: str,
        camera: str = "",
        negative_prompt: str = "",
        **kwargs: Any,
    ) -> ModelAdaptResult:
        return adapt_prompt_for_model(
            prompt_text,
            target_model=target_model,
            camera=camera,
            negative_prompt=negative_prompt,
        )

    async def aextract(self, **kwargs: Any) -> ModelAdaptResult:
        return self.extract(**kwargs)


__all__ = ["ModelAdapterAgent", "ModelAdaptResult", "adapt_prompt_for_model"]
