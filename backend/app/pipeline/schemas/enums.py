"""共享枚举 —— 跨三层 Schema 复用的取值集合。"""

from __future__ import annotations

from enum import Enum


class TargetModel(str, Enum):
    """????????????
    kling / jimeng
    """
    KLING = "kling"
    JIMENG = "jimeng"


class FramingStyle(str, Enum):
    """景别 —— 镜头取景范围。"""
    EXTREME_WIDE = "extreme_wide"   # 全大全远
    WIDE = "wide"                   # 远景
    FULL = "full"                   # 全景
    MEDIUM_WIDE = "medium_wide"     # 中远景
    MEDIUM = "medium"               # 中景
    MEDIUM_CLOSE = "medium_close"   # 中近景
    CLOSE_UP = "close_up"           # 近景/特写
    EXTREME_CLOSE_UP = "extreme_close_up"


class VisualStyle(str, Enum):
    """视觉风格。"""
    CINEMATIC = "cinematic"
    ANIME = "anime"
    REALISTIC = "realistic"
    OIL_PAINTING = "oil_painting"
    WATERCOLOR = "watercolor"
    PIXEL_ART = "pixel_art"
    NOIR = "noir"
    CYBERPUNK = "cyberpunk"
    FANTASY = "fantasy"
    DOCUMENTARY = "documentary"


class MoodTone(str, Enum):
    """情绪基调。"""
    DARK = "dark"
    HOPEFUL = "hopeful"
    TENSE = "tense"
    MYSTERIOUS = "mysterious"
    EPIC = "epic"
    WHIMSICAL = "whimsical"
    MELANCHOLIC = "melancholic"
    ROMANTIC = "romantic"
    HORROR = "horror"
    NEUTRAL = "neutral"


class AspectRatio(str, Enum):
    """画幅比例。"""
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_1_1 = "1:1"
    RATIO_21_9 = "21:9"
    RATIO_4_3 = "4:3"


__all__ = [
    "TargetModel",
    "FramingStyle",
    "VisualStyle",
    "MoodTone",
    "AspectRatio",
]
