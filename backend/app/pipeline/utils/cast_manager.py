"""全局演员表管理 —— 跨章节角色持久化。

维护 cast.json 文件，支持：
- 读取已有演员表（pipeline 启动时）
- 合并新角色（Step 1 完成后）
- 更新服装（同角色不同章节服饰变化）
- 保存更新后的演员表（pipeline 结束时）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import get_logger

logger = get_logger(__name__)

# 默认 cast.json 路径
DEFAULT_CAST_FILE = "output/cast.json"


class CastManager:
    """全局演员表管理器。

    cast.json 结构:
    {
      "陆沉": {
        "character_id": "char_001",
        "role": "主角",
        "base_appearance": "20岁，178cm，黑色短发，苍白肤色...",
        "character_sheet": "完整演员表级描述...",
        "costumes": {
          "第001章": "洗得发白的深蓝色连帽卫衣+黑色薄款夹克",
          "第005章": "黑色西装+白衬衫+红领带"
        },
        "first_chapter": "第001章",
        "reference_image_url": ""
      },
      ...
    }
    """

    def __init__(self, cast_file: str | Path = DEFAULT_CAST_FILE):
        self.cast_file = Path(cast_file)
        self.cast_data: dict[str, dict[str, Any]] = {}
        self._dirty = False  # 标记是否有修改需要保存

    def load(self) -> dict[str, dict[str, Any]]:
        """从 cast.json 加载全局演员表。"""
        if self.cast_file.exists():
            try:
                raw = self.cast_file.read_text(encoding="utf-8")
                self.cast_data = json.loads(raw)
                logger.info(
                    "[CastManager] ✅ 已加载全局演员表: %s (%d 角色)",
                    self.cast_file, len(self.cast_data),
                )
            except Exception as e:
                logger.warning("[CastManager] 加载 cast.json 失败: %s, 使用空演员表", e)
                self.cast_data = {}
        else:
            logger.info("[CastManager] cast.json 不存在, 使用空演员表: %s", self.cast_file)
            self.cast_data = {}
        return self.cast_data

    def save(self) -> Path:
        """保存全局演员表到 cast.json。"""
        if not self._dirty:
            logger.info("[CastManager] 演员表无修改, 跳过保存")
            return self.cast_file

        self.cast_file.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self.cast_data, ensure_ascii=False, indent=2)
        self.cast_file.write_text(raw, encoding="utf-8")
        logger.info(
            "[CastManager] ✅ 全局演员表已保存: %s (%d 角色)",
            self.cast_file, len(self.cast_data),
        )
        return self.cast_file

    def merge_characters(
        self,
        characters: list[dict[str, Any]],
        chapter_title: str,
    ) -> dict[str, str]:
        """将本章角色合并到全局演员表。

        Args:
            characters: Step 1 输出的角色列表 (每个元素是 Character.model_dump())
            chapter_title: 当前章节标题

        Returns:
            合并结果摘要: {"new": [...], "updated": [...], "unchanged": [...]}
        """
        result = {"new": [], "updated": [], "unchanged": []}

        for char in characters:
            name = char.get("name", "")
            if not name:
                continue

            if name not in self.cast_data:
                # 新角色: 注册到全局演员表
                self.cast_data[name] = {
                    "character_id": char.get("character_id", ""),
                    "role": char.get("role", ""),
                    "base_appearance": char.get("appearance", ""),
                    "character_sheet": char.get("character_sheet", "") or char.get("visual_anchor", ""),
                    "costumes": {},
                    "first_chapter": chapter_title,
                    "reference_image_url": char.get("reference_image_url", ""),
                }
                # 从 character_sheet 中提取服装信息
                self._extract_costume(name, char.get("character_sheet", ""), chapter_title)
                result["new"].append(name)
                self._dirty = True
                logger.info("[CastManager] ✨ 新角色注册: %s (来自 %s)", name, chapter_title)
            else:
                # ????: ????????? character_sheet
                existing = self.cast_data[name]
                updated = False

                # character_sheet ????????????
                character_desc = char.get("character_sheet", "") or char.get("visual_anchor", "")

                # ?????????
                costume = self._extract_costume(name, character_desc, chapter_title)
                if costume:
                    updated = True

                if updated:
                    result["updated"].append(name)
                    self._dirty = True
                    logger.info("[CastManager] 🔄 角色更新: %s (来自 %s)", name, chapter_title)
                else:
                    result["unchanged"].append(name)

        if result["new"]:
            logger.info("[CastManager] 新增角色: %s", result["new"])
        if result["updated"]:
            logger.info("[CastManager] 更新角色: %s", result["updated"])

        return result

    def _extract_costume(self, char_name: str, description: str, chapter: str) -> str | None:
        """从角色描述中提取服装信息。

        简单启发式: 查找服装相关关键词后的描述。
        """
        if not description:
            return None

        # 服装关键词
        costume_keywords = [
            "穿着", "穿", "身穿", "身着", "服饰", "服装", "外套", "夹克",
            "卫衣", "西装", "衬衫", "裙子", "裤子", "大衣", "风衣",
        ]

        # 查找服装描述
        for kw in costume_keywords:
            idx = description.find(kw)
            if idx >= 0:
                # 提取服装描述（截取到句号或结尾）
                costume_text = description[idx:]
                end_idx = costume_text.find("。")
                if end_idx > 0:
                    costume_text = costume_text[:end_idx]
                # 限制长度
                if len(costume_text) > 10:
                    existing_costumes = self.cast_data.get(char_name, {}).get("costumes", {})
                    existing_costumes[chapter] = costume_text.strip()
                    self.cast_data.setdefault(char_name, {})["costumes"] = existing_costumes
                    return costume_text.strip()

        return None

    def get_character(self, name: str) -> dict[str, Any] | None:
        """获取指定角色的全局演员表数据。"""
        return self.cast_data.get(name)

    def get_character_sheet(self, name: str) -> str:
        """获取角色的 character_sheet（基础外貌）。"""
        char = self.cast_data.get(name)
        if char:
            return char.get("character_sheet", "") or char.get("base_appearance", "")
        return ""

    def get_costume_for_chapter(self, name: str, chapter: str) -> str:
        """获取角色在指定章节的服装描述。"""
        char = self.cast_data.get(name)
        if char:
            costumes = char.get("costumes", {})
            return costumes.get(chapter, "")
        return ""

    def get_all_names(self) -> list[str]:
        """获取所有已注册角色名。"""
        return list(self.cast_data.keys())

    def to_excel_data(self) -> list[dict[str, str]]:
        """导出演员表数据供 Excel 使用。"""
        rows = []
        for name, data in self.cast_data.items():
            rows.append({
                "name": name,
                "role": data.get("role", ""),
                "character_sheet": data.get("character_sheet", "") or data.get("base_appearance", ""),
                "reference_image_url": data.get("reference_image_url", ""),
                "first_chapter": data.get("first_chapter", ""),
                "costumes": json.dumps(data.get("costumes", {}), ensure_ascii=False),
            })
        return rows


__all__ = ["CastManager", "DEFAULT_CAST_FILE"]
