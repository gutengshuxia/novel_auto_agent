"""故事板分镜卡片生成器 —— 为视频 Prompt 生成视觉参考卡片。

功能：
1. 从视频 Prompt 提取关键信息（角色/场景/镜头/风格）
2. 生成故事板卡片提示词（角色参考/场景风格/镜头构图）
3. 调用 DALL-E 3 API 生成参考图片（可选）
4. 导出到 Excel 或单独目录
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import get_logger

logger = get_logger(__name__)


class StoryboardCardGenerator:
    """故事板分镜卡片生成器。

    用法：
        generator = StoryboardCardGenerator()
        cards = generator.generate_cards_from_prompt(
            shot_id="shot_001",
            video_prompt="[0-2.5s] ...",
            character_sheets={"陆沉": "..."},
            scene_description="昏暗出租屋...",
            director_style="王家卫风格"
        )
        # 生成图片（可选）
        generator.generate_images(cards, output_dir="output/cards/")
        # 导出到 Excel
        generator.export_to_excel(cards, "output/storyboard.xlsx")
    """

    def __init__(self, enable_image_generation: bool = False):
        """
        Args:
            enable_image_generation: 是否启用 DALL-E 3 图片生成（需要 OPENAI_API_KEY）
        """
        self.enable_image_generation = enable_image_generation
        self.client = None
        if enable_image_generation:
            try:
                from openai import OpenAI
                self.client = OpenAI()
                logger.info("[CardGenerator] ✅ DALL-E 3 图片生成已启用")
            except Exception as e:
                logger.warning("[CardGenerator] DALL-E 3 初始化失败: %s, 图片生成已禁用", e)
                self.enable_image_generation = False

    def generate_cards_from_prompt(
        self,
        shot_id: str,
        video_prompt: str,
        character_sheets: dict[str, str],
        scene_description: str = "",
        director_style: str = "",
    ) -> list[dict[str, Any]]:
        """从视频 Prompt 生成故事板卡片。

        Args:
            shot_id: 镜头 ID（如 "shot_001"）
            video_prompt: 完整的视频 Prompt 文本
            character_sheets: 角色演员表 {角色名: character_sheet}
            scene_description: 场景描述
            director_style: 导演风格参考

        Returns:
            卡片列表，每个卡片包含 {type, title, prompt, image_url (可选)}
        """
        cards = []

        # 提取角色名（从 @角色名 或文本中）
        characters = self._extract_characters(video_prompt, character_sheets)

        # 1. 角色参考卡（每个角色一张）
        for char_name in characters:
            char_sheet = character_sheets.get(char_name, "")
            card = self._generate_character_card(shot_id, char_name, char_sheet, video_prompt)
            cards.append(card)

        # 2. 场景风格参考卡
        if scene_description or self._has_scene_info(video_prompt):
            card = self._generate_scene_card(shot_id, scene_description, video_prompt, director_style)
            cards.append(card)

        # 3. 镜头构图参考卡
        card = self._generate_shot_card(shot_id, video_prompt, director_style)
        cards.append(card)

        logger.info("[CardGenerator] ✅ 生成 %d 张卡片 (shot=%s)", len(cards), shot_id)
        return cards

    def _extract_characters(self, video_prompt: str, character_sheets: dict[str, str]) -> list[str]:
        """从视频 Prompt 中提取角色名。"""
        # 优先提取 @角色名
        at_mentions = re.findall(r"@(\S+)", video_prompt)
        characters = list(set(at_mentions))

        # 如果没有 @引用，尝试从 character_sheets 中匹配
        if not characters:
            for char_name in character_sheets.keys():
                if char_name in video_prompt:
                    characters.append(char_name)

        return characters[:3]  # 最多 3 个角色

    def _has_scene_info(self, video_prompt: str) -> bool:
        """检查视频 Prompt 是否包含场景信息。"""
        scene_keywords = ["出租屋", "房间", "街道", "办公室", "山间", "林间", "雾气", "昏暗"]
        return any(kw in video_prompt for kw in scene_keywords)

    def _generate_character_card(
        self,
        shot_id: str,
        char_name: str,
        char_sheet: str,
        video_prompt: str,
    ) -> dict[str, Any]:
        """生成角色参考卡。"""
        # 从 video_prompt 中提取当前场景的姿态/动作/光线
        pose_info = self._extract_pose_info(video_prompt, char_name)

        card_prompt = f"""角色参考图 - {char_name}（{shot_id} 场景）

正面半身像，{char_sheet}
姿态：{pose_info.get('pose', '自然站立')}
光线：{pose_info.get('lighting', '自然光')}
色调：{pose_info.get('tone', '电影感色调')}
背景：虚化的场景环境

风格：cinematic portrait, film grain, soft focus background, 
      真实皮肤质感，真实布料质感，无CG感，无AI感，实拍电影质感"""

        return {
            "type": "character",
            "shot_id": shot_id,
            "title": f"角色参考 - {char_name}",
            "prompt": card_prompt,
            "image_url": None,
            "image_path": None,
        }

    def _generate_scene_card(
        self,
        shot_id: str,
        scene_description: str,
        video_prompt: str,
        director_style: str,
    ) -> dict[str, Any]:
        """生成场景风格参考卡。"""
        # 从 video_prompt 提取场景关键词
        scene_info = self._extract_scene_info(video_prompt)

        card_prompt = f"""场景风格参考 - {shot_id}

全景广角镜头，展现场景全貌。
环境：{scene_description or scene_info.get('environment', '场景环境')}
光线：{scene_info.get('lighting', '自然光+人造光混合')}
色调：{scene_info.get('tone', '电影感色调')}
氛围：{scene_info.get('mood', '压抑/紧张/孤独')}
质感：真实墙壁纹理，真实布料质感，真实空气感

风格参考：{director_style or '电影实拍质感'}
film grain，不锐化，无CG感，无AI感，实拍电影质感"""

        return {
            "type": "scene",
            "shot_id": shot_id,
            "title": f"场景参考 - {shot_id}",
            "prompt": card_prompt,
            "image_url": None,
            "image_path": None,
        }

    def _generate_shot_card(
        self,
        shot_id: str,
        video_prompt: str,
        director_style: str,
    ) -> dict[str, Any]:
        """生成镜头构图参考卡。"""
        # 从 video_prompt 提取镜头信息
        shot_info = self._extract_shot_info(video_prompt)

        card_prompt = f"""镜头构图参考 - {shot_id}

景别：{shot_info.get('framing', 'wide shot')}
机位：{shot_info.get('camera_angle', '平视')}
构图：{shot_info.get('composition', '三分法构图')}
光线：{shot_info.get('lighting', '单源顶光')}
色调：{shot_info.get('tone', '冷蓝偏暗')}
焦点：{shot_info.get('focus', '主体清晰，背景虚化')}
运动：{shot_info.get('movement', '固定镜头')}

风格：{director_style or 'cinematic shot, film grain'}
真实实拍感，无CG，无AI感，不锐化"""

        return {
            "type": "shot",
            "shot_id": shot_id,
            "title": f"镜头参考 - {shot_id}",
            "prompt": card_prompt,
            "image_url": None,
            "image_path": None,
        }

    def _extract_pose_info(self, video_prompt: str, char_name: str) -> dict[str, str]:
        """从视频 Prompt 提取角色姿态信息。"""
        info = {"pose": "自然站立", "lighting": "自然光", "tone": "电影感色调"}

        # 提取姿态关键词
        pose_keywords = ["弓背", "坐", "站", "低头", "抬头", "转身", "蹲"]
        for kw in pose_keywords:
            if kw in video_prompt:
                # 提取包含该关键词的句子
                match = re.search(rf"{char_name}[^。]*{kw}[^。]*", video_prompt)
                if match:
                    info["pose"] = match.group(0)[:50]
                    break

        # 提取光线
        if "白炽灯" in video_prompt:
            info["lighting"] = "冷白色顶光（白炽灯）"
        elif "侧光" in video_prompt:
            info["lighting"] = "侧光"
        elif "逆光" in video_prompt:
            info["lighting"] = "逆光"

        # 提取色调
        if "冷蓝" in video_prompt:
            info["tone"] = "冷蓝偏暗"
        elif "暖黄" in video_prompt:
            info["tone"] = "暖黄"

        return info

    def _extract_scene_info(self, video_prompt: str) -> dict[str, str]:
        """从视频 Prompt 提取场景信息。"""
        info = {
            "environment": "场景环境",
            "lighting": "自然光",
            "tone": "电影感色调",
            "mood": "中性",
        }

        # 提取环境
        if "出租屋" in video_prompt:
            info["environment"] = "昏暗出租屋，墙皮剥落，旧木椅，简陋木桌"
        elif "办公室" in video_prompt:
            info["environment"] = "办公室，金属桌，文件"

        # 提取光线
        if "白炽灯" in video_prompt:
            info["lighting"] = "单源白炽灯顶光，冷白色"
        elif "侧光" in video_prompt:
            info["lighting"] = "侧光，高对比度"

        # 提取色调
        if "冷蓝" in video_prompt:
            info["tone"] = "冷蓝偏暗，低饱和度"
        elif "暖黄" in video_prompt:
            info["tone"] = "暖黄，低饱和度"

        # 提取氛围
        if "压抑" in video_prompt or "孤独" in video_prompt:
            info["mood"] = "压抑、孤独"
        elif "紧张" in video_prompt:
            info["mood"] = "紧张、危险"

        return info

    def _extract_shot_info(self, video_prompt: str) -> dict[str, str]:
        """从视频 Prompt 提取镜头信息。"""
        info = {
            "framing": "wide shot",
            "camera_angle": "平视",
            "composition": "三分法构图",
            "lighting": "自然光",
            "tone": "电影感色调",
            "focus": "主体清晰",
            "movement": "固定镜头",
        }

        # 提取景别
        if "wide shot" in video_prompt or "广角" in video_prompt:
            info["framing"] = "wide shot (24mm)"
        elif "medium shot" in video_prompt or "中景" in video_prompt:
            info["framing"] = "medium shot (50mm)"
        elif "close-up" in video_prompt or "特写" in video_prompt:
            info["framing"] = "close-up (85mm)"

        # 提取机位
        if "低角度" in video_prompt or "仰拍" in video_prompt:
            info["camera_angle"] = "低角度仰拍"
        elif "高角度" in video_prompt or "俯拍" in video_prompt:
            info["camera_angle"] = "高角度俯拍"

        # 提取构图
        if "三分法" in video_prompt:
            info["composition"] = "三分法构图"
        elif "居中" in video_prompt:
            info["composition"] = "居中构图"

        # 提取运动
        if "static" in video_prompt or "固定" in video_prompt:
            info["movement"] = "固定镜头 (static)"
        elif "dolly" in video_prompt:
            info["movement"] = "推拉镜头 (dolly)"
        elif "pan" in video_prompt:
            info["movement"] = "摇镜头 (pan)"

        return info

    def generate_images(self, cards: list[dict[str, Any]], output_dir: str | Path) -> list[dict[str, Any]]:
        """为卡片生成图片（使用 DALL-E 3）。

        Args:
            cards: 卡片列表
            output_dir: 图片输出目录

        Returns:
            更新后的卡片列表（含 image_url 和 image_path）
        """
        if not self.enable_image_generation or not self.client:
            logger.warning("[CardGenerator] 图片生成未启用，跳过")
            return cards

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        for card in cards:
            try:
                logger.info("[CardGenerator] 生成图片: %s", card["title"])
                response = self.client.images.generate(
                    model="dall-e-3",
                    prompt=card["prompt"],
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                image_url = response.data[0].url
                card["image_url"] = image_url

                # 下载图片（可选）
                # import requests
                # image_data = requests.get(image_url).content
                # image_path = out_dir / f"{card['shot_id']}_{card['type']}.png"
                # image_path.write_bytes(image_data)
                # card["image_path"] = str(image_path)

                logger.info("[CardGenerator] ✅ 图片已生成: %s", image_url[:80])
            except Exception as e:
                logger.error("[CardGenerator] 图片生成失败: %s", e)

        return cards


__all__ = ["StoryboardCardGenerator"]
