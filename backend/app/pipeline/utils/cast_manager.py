"""全局演员表管理 —— 跨章节角色持久化。

维护 cast.json 文件，支持：
- 读取已有演员表（pipeline 启动时）
- 合并新角色（Step 1 完成后）
- 更新服装（同角色不同章节服饰变化）
- 保存更新后的演员表（pipeline 结束时）
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from . import get_logger

logger = get_logger(__name__)

# 默认 cast.json 路径
DEFAULT_CAST_FILE = "output/cast.json"

# 按文件路径缓存的锁, 避免多个 CastManager 实例竞争同一文件
_file_locks: dict[str, threading.Lock] = {}
_file_locks_lock = threading.Lock()


def _get_file_lock(file_path: str) -> threading.Lock:
    """获取某个文件专用的线程锁, 全局唯一。"""
    with _file_locks_lock:
        if file_path not in _file_locks:
            _file_locks[file_path] = threading.Lock()
        return _file_locks[file_path]


class CastManager:
    """全局演员表管理器, 支持跨进程/跨线程安全。

    所有对 cast.json 的读/写均通过文件锁同步;
    内部 cast_data 也被 _lock 保护, 防止竞态。

    cast.json 结构:
    {
      "角色名": {
        "character_id": "char_001",
        "role": "主角",
        "base_appearance": "20岁, 178cm, …",
        "character_sheet": "完整演员表级描述…",
        "costumes": {},
        "first_chapter": "第001章",
        "reference_image_url": ""
      },
      ...
    }
    """

    def __init__(self, cast_file: str | Path = DEFAULT_CAST_FILE):
        self.cast_file = Path(cast_file)
        self._file_lock = _get_file_lock(str(self.cast_file.resolve()))
        self._lock = threading.Lock()
        self.cast_data: dict[str, dict[str, Any]] = {}
        self._dirty = False

    # ---------- 文件 DML ----------

    def load(self) -> dict[str, dict[str, Any]]:
        """从 cast.json 同步读取 (线程+文件安全)。"""
        with self._lock, self._file_lock:
            self._load_unlocked()
            return dict(self.cast_data)

    def _load_unlocked(self) -> None:
        """内部不锁版本, 调用者需持 self._lock 与 self._file_lock。"""
        if self.cast_file.exists():
            try:
                if self.cast_file.stat().st_size == 0:
                    logger.warning(
                        "[CastManager] cast.json 为空, 使用空演员表: %s",
                        self.cast_file,
                    )
                    self.cast_data = {}
                    return
                raw = self.cast_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    self.cast_data = data
                else:
                    logger.warning(
                        "[CastManager] cast.json 顶层不是对象 (type=%s), 回退空演员表",
                        type(data).__name__
                    )
                    self.cast_data = {}
                logger.info(
                    "[CastManager] 已加载全局演员表: %s (%d 角色)",
                    self.cast_file, len(self.cast_data),
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(
                    "[CastManager] cast.json 格式错误: %s, 回退空演员表", e
                )
                self.cast_data = {}
            except OSError as e:
                logger.warning(
                    "[CastManager] 读取 cast.json 失败: %s, 使用空演员表", e
                )
                self.cast_data = {}
        else:
            logger.info(
                "[CastManager] cast.json 不存在, 使用空演员表: %s",
                self.cast_file
            )
            self.cast_data = {}

    def save(self) -> Path:
        """保存到 cast.json (原子写入: 临时文件 → 重命名)。"""
        with self._lock:
            if not self._dirty:
                logger.info("[CastManager] 演员表无修改, 跳过保存")
                return self.cast_file

            self.cast_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cast_file.with_suffix(".json.tmp")
            raw = json.dumps(self.cast_data, ensure_ascii=False, indent=2)

            with self._file_lock:
                try:
                    tmp_path.write_text(raw, encoding="utf-8")
                    os.replace(tmp_path, self.cast_file)
                    logger.info(
                        "[CastManager] ✅ 全局演员表已保存: %s (%d 角色)",
                        self.cast_file, len(self.cast_data),
                    )
                except Exception:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                    raise

            self._dirty = False
            return self.cast_file

    # ---- 业务方法 ----

    def merge_characters(
        self,
        characters: list[dict[str, Any]],
        chapter_title: str,
    ) -> dict[str, Any]:
        """将本章角色合并到全局演员表(线程安全)。"""
        with self._lock:
            result = self._merge_characters_unlocked(characters, chapter_title)
            return result

    def _merge_characters_unlocked(
        self,
        characters: list[dict[str, Any]],
        chapter_title: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"new": [], "updated": [], "unchanged": []}

        for char in characters:
            name = char.get("name", "")
            if not name:
                continue

            if name not in self.cast_data:
                # 新角色注册
                self.cast_data[name] = {
                    "character_id": char.get("character_id", ""),
                    "role": char.get("role", ""),
                    "base_appearance": char.get("appearance", ""),
                    "character_sheet": char.get("character_sheet", "")
                    or char.get("visual_anchor", ""),
                    "costumes": {},
                    "first_chapter": chapter_title,
                    "reference_image_url": char.get("reference_image_url", ""),
                }
                self._extract_costume_unlocked(
                    name, char.get("character_sheet", ""), chapter_title
                )
                result["new"].append(name)
                self._dirty = True
                logger.info(
                    "[CastManager] ✨ 新角色注册: %s (来自 %s)",
                    name, chapter_title
                )
            else:
                updated = False
                character_desc = char.get("character_sheet", "") or char.get(
                    "visual_anchor", ""
                )
                costume = self._extract_costume_unlocked(
                    name, character_desc, chapter_title
                )
                if costume:
                    updated = True

                if updated:
                    result["updated"].append(name)
                    self._dirty = True
                    logger.info(
                        "[CastManager] 🔄 角色更新: %s (来自 %s)",
                        name, chapter_title
                    )
                else:
                    result["unchanged"].append(name)

        if result["new"]:
            logger.info("[CastManager] 新增角色: %s", result["new"])
        if result["updated"]:
            logger.info("[CastManager] 更新角色: %s", result["updated"])

        return result

    # ---- 查询 API (线程安全) ----

    def get_character(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            return self.cast_data.get(name)

    def get_character_sheet(self, name: str) -> str:
        with self._lock:
            char = self.cast_data.get(name)
            if char:
                return char.get("character_sheet", "") or char.get(
                    "base_appearance", ""
                )
            return ""

    def get_costume_for_chapter(self, name: str, chapter: str) -> str:
        with self._lock:
            char = self.cast_data.get(name)
            if char:
                costumes = char.get("costumes", {})
                return costumes.get(chapter, "")
            return ""

    def get_all_names(self) -> list[str]:
        with self._lock:
            return list(self.cast_data.keys())

    def to_goog_data(self) -> list[dict[str, str]]:
        with self._lock:
            return self._to_excel_data_unlocked()

    def _to_excel_data_unlocked(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for name, data in self.cast_data.items():
            rows.append(
                {
                    "name": name,
                    "role": data.get("role", ""),
                    "character_sheet": data.get("character_sheet", "")
                    or data.get("base_appearance", ""),
                    "reference_image_url": data.get("reference_image_url", ""),
                    "first_chapter": data.get("first_chapter", ""),
                    "costumes": json.dumps(
                        data.get("costumes", {}), ensure_ascii=False
                    ),
                }
            )
        return rows

    # ---- 内部方法 ----

    def _extract_costume(
        self, char_name: str, description: str, chapter: str
    ) -> str | None:
        with self._lock:
            return self._extract_costume_unlocked(char_name, description, chapter)

    def _extract_costume_unlocked(
        self, char_name: str, description: str, chapter: str
    ) -> str | None:
        """从描述提取服装, 调用者需持有 self._lock。"""
        if not description:
            return None

        costume_keywords = [
            "穿着", "穿", "身穿", "身着", "服饰", "服装",
            "外衣", "夹克", "卫衣", "西装", "衬衫",
            "裙子", "裤子", "大衣", "风衣",
        ]

        for kw in costume_keywords:
            idx = description.find(kw)
            if idx >= 0:
                costume_text = description[idx:]
                end_idx = costume_text.find("。")
                if end_idx > 0:
                    costume_text = costume_text[:end_idx]
                if len(costume_text) > 10:
                    existing = self.cast_data.setdefault(char_name, {}).setdefault(
                        "costumes", {}
                    )
                    existing[chapter] = costume_text.strip()
                    return costume_text.strip()

        return None


__all__ = ["CastManager", "DEFAULT_CAST_FILE"]
