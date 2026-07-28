"""导演风格加载器 — 加载、查询、组合 31 位导演的创作风格。"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ── 协作模式 ───────────────────────────────────────
class CollaborationMode(str, Enum):
    SEQUENTIAL = "sequential"       # 顺序链: 逐位风格叠加
    DEBATE_VOTE = "debate_vote"     # 辩论投票: 多位导演各自出方案,投票融合
    CHAIRMAN = "chairman"           # 主席团: 首席导演统筹,其他辅助


# ── 导演分类 ───────────────────────────────────────
class DirectorCategory(str, Enum):
    CHINESE = "华语"
    HOLLYWOOD = "好莱坞"
    EUROPEAN = "欧洲"
    JAPANESE = "日本"
    KOREAN = "韩国"
    OTHER = "其他"


# ── 导演风格数据 ───────────────────────────────────────
@dataclass
class DirectorStyle:
    """单一位导演的创作风格描述。"""
    id: str                     # 如 wongkarwai-perspective
    name_zh: str                # 中文名
    name_en: str = ""           # 英文名
    category: DirectorCategory = DirectorCategory.CHINESE
    core_style: str = ""        # 核心风格描述
    keywords: list[str] = field(default_factory=list)
    representative_works: list[str] = field(default_factory=list)
    visual_signature: str = ""  # 视觉签名
    narrative_traits: str = ""  # 叙事特点
    genre_strength: list[str] = field(default_factory=list)  # 擅长类型
    full_skill: str = ""        # 完整 SKILL.md 内容
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def director_prompt(self) -> str:
        """生成注入 LLM 的导演风格 prompt 片段。"""
        return self.full_skill if self.full_skill else self._build_minimal_prompt()

    def _build_minimal_prompt(self) -> str:
        parts = [f"## 导演: {self.name_zh} ({self.name_en})"]
        if self.core_style:
            parts.append(f"**风格**: {self.core_style}")
        if self.keywords:
            parts.append(f"**关键词**: {', '.join(self.keywords)}")
        if self.visual_signature:
            parts.append(f"**视觉**: {self.visual_signature}")
        if self.narrative_traits:
            parts.append(f"**叙事**: {self.narrative_traits}")
        return "\n".join(parts)


# ── 导演注册表 ─────────────────────────────────────────────────
#   格式: { "id": DirectorStyle, ... }
DIRECTOR_REGISTRY: dict[str, DirectorStyle] = {}

# 导演 ID → 中文名映射 (用于按中文名查询)
_ID_TO_NAME: dict[str, str] = {}

# 手动维护的导演元数据表 (从 DirectorAgents README 提取)
_DIRECTOR_META: dict[str, dict] = {
    # ── 华语导演 ──
    "zhangyimou-perspective":         {"name_zh": "张艺谋", "category": "华语", "works": ["红高粱", "活着", "英雄"], "style": "色彩与仪式感的极致运用", "keywords": ["色彩", "史诗", "仪式感"]},
    "chenkaige-perspective":          {"name_zh": "陈凯歌", "category": "华语", "works": ["霸王别姬", "黄土地"], "style": "人文思辨与悲剧美学", "keywords": ["人文", "悲剧", "历史"]},
    "jiangwen-perspective":           {"name_zh": "姜文", "category": "华语", "works": ["让子弹飞", "阳光灿烂的日子"], "style": "荒诞天才的魔幻现实主义", "keywords": ["荒诞", "魔幻", "黑色幽默"]},
    "jiazhangke-perspective":         {"name_zh": "贾樟柯", "category": "华语", "works": ["小武", "山河故人"], "style": "社会变迁的纪实凝视", "keywords": ["纪实", "社会", "写实"]},
    "wongkarwai-perspective":         {"name_zh": "王家卫", "category": "华语", "works": ["花样年华", "重庆森林"], "style": "感官诗学与时间变奏", "keywords": ["抽帧", "迷离光影", "时间流逝"]},
    "tsuihark-perspective":           {"name_zh": "徐克", "category": "华语", "works": ["倩女幽魂", "黄飞鸿"], "style": "天马行空的魔幻江湖", "keywords": ["武侠", "奇幻", "想象"]},
    "johnnieto-perspective":          {"name_zh": "杜琪峰", "category": "华语", "works": ["枪火", "黑社会"], "style": "冷峻宿命的黑色交响乐", "keywords": ["黑色", "宿命", "冷峻"]},
    "johnwoo-perspective":            {"name_zh": "吴宇森", "category": "华语", "works": ["英雄本色", "喋血双雄"], "style": "暴力美学与侠义江湖", "keywords": ["暴力美学", "江湖", "双雄"]},
    "stephenchow-perspective":        {"name_zh": "周星驰", "category": "华语", "works": ["大话西游", "功夫"], "style": "荒诞喜剧中的人性悲悯", "keywords": ["无厘头", "喜剧", "悲悯"]},
    "peterchan-perspective":          {"name_zh": "陈可辛", "category": "华语", "works": ["甜蜜蜜", "中国合伙人"], "style": "精细平衡的优质商业叙事", "keywords": ["商业", "情感", "叙事"]},
    "edwardyang-perspective":         {"name_zh": "杨德昌", "category": "华语", "works": ["牯岭街少年杀人事件", "一一"], "style": "精确解剖现代都市病", "keywords": ["社会", "都市", "写实"]},
    "houhsiaohsien-perspective":      {"name_zh": "侯孝贤", "category": "华语", "works": ["悲情城市", "刺客聂隐娘"], "style": "东方美学的长镜诗篇", "keywords": ["长镜头", "东方美学", "诗意"]},
    "anglee-perspective":             {"name_zh": "李安", "category": "华语", "works": ["卧虎藏龙", "少年派的奇幻漂流"], "style": "无界探索的文化桥梁", "keywords": ["文化融合", "情感", "细腻"]},

    # ── 好莱坞导演 ──
    "stevenspielberg-perspective":    {"name_zh": "史蒂文·斯皮尔伯格", "category": "好莱坞", "works": ["辛德勒的名单", "侏罗纪公园"], "style": "童真与人文的造梦大师", "keywords": ["童真", "人文", "造梦"]},
    "christophernolan-perspective":   {"name_zh": "克里斯托弗·诺兰", "category": "好莱坞", "works": ["盗梦空间", "星际穿越"], "style": "高概念烧脑的时空游戏", "keywords": ["时间", "结构", "烧脑"]},
    "quentintarantino-perspective":   {"name_zh": "昆汀·塔伦蒂诺", "category": "好莱坞", "works": ["低俗小说", "无耻混蛋"], "style": "话痨暴力与拼贴狂欢", "keywords": ["暴力", "对话", "拼贴"]},
    "franciscoppola-perspective":     {"name_zh": "弗朗西斯·科波拉", "category": "好莱坞", "works": ["教父", "现代启示录"], "style": "现代启示录与家族史诗", "keywords": ["史诗", "家族", "力量"]},
    "jamescameron-perspective":       {"name_zh": "詹姆斯·卡梅隆", "category": "好莱坞", "works": ["阿凡达", "泰坦尼克号"], "style": "技术先驱使的感官革命", "keywords": ["技术", "视觉", "大片"]},
    "davidfincher-perspective":       {"name_zh": "大卫·芬奇", "category": "好莱坞", "works": ["七宗罪", "社交网络"], "style": "形式的极致与黑暗的坚韧", "keywords": ["黑色", "精准", "悬疑"]},
    "woodyallen-perspective":         {"name_zh": "伍迪·艾伦", "category": "好莱坞", "works": ["安妮·霍尔", "午夜巴黎"], "style": "知识分子幽默与中产喜剧", "keywords": ["幽默", "知识分子", "爱情"]},

    # ── 欧洲艺术大师 ──
    "ingmarbergman-perspective":      {"name_zh": "英格玛·伯格曼", "category": "欧洲", "works": ["第七封印", "野草莓"], "style": "存在主义与信仰拷问", "keywords": ["存在主义", "信仰", "死亡"]},
    "andreitarkovsky-perspective":    {"name_zh": "安德烈·塔可夫斯基", "category": "欧洲", "works": ["乡愁", "镜子"], "style": "时间雕刻的诗意影像", "keywords": ["诗意", "时间", "精神"]},
    "federicofellini-perspective":    {"name_zh": "费德里科·费里尼", "category": "欧洲", "works": ["八部半", "甜蜜的生活"], "style": "梦境与狂欢的巴洛克", "keywords": ["梦境", "狂欢", "自传"]},
    "luisbunuel-perspective":         {"name_zh": "路易斯·布努埃尔", "category": "欧洲", "works": ["安达卢西亚犬", "资产阶级的审慎魅力"], "style": "超现实主义先驱", "keywords": ["超现实", "讽刺", "颠覆"]},
    "michelangeloantonioni-perspective": {"name_zh": "米开朗基罗·安东尼奥尼", "category": "欧洲", "works": ["放大", "红色沙漠"], "style": "现代疏离与空间美学", "keywords": ["疏离", "空间", "现代"]},

    # ── 日韩导演 ──
    "akirakurosawa-perspective":      {"name_zh": "黑泽明", "category": "日本", "works": ["七武士", "罗生门"], "style": "武士道精神与人性史诗", "keywords": ["史诗", "人性", "武士"]},
    "hayaomiyazaki-perspective":      {"name_zh": "宫崎骏", "category": "日本", "works": ["千与千寻", "龙猫"], "style": "自然与人文的筑梦大师", "keywords": ["动画", "自然", "童真"]},
    "ozuyasujiro-perspective":        {"name_zh": "小津安二郎", "category": "日本", "works": ["东京物语", "晚春"], "style": "低机位的静观日常", "keywords": ["家庭", "日常", "低机位"]},
    "hirokazukoreeda-perspective":    {"name_zh": "是枝裕和", "category": "日本", "works": ["小偷家族", "步履不停"], "style": "温柔的日常真相", "keywords": ["家庭", "温柔", "日常"]},
    "bongjoonho-perspective":         {"name_zh": "奉俊昊", "category": "韩国", "works": ["寄生虫", "杀人回忆"], "style": "类型混搭的社会寓言", "keywords": ["社会", "类型", "反转"]},
    "parkchanwook-perspective":       {"name_zh": "朴赞郁", "category": "韩国", "works": ["老男孩", "小姐"], "style": "极端恨与极致美的惊悚美学", "keywords": ["复仇", "美学", "悬疑"]},

    # ── 其他 ──
    "luisbunuel-perspective":         {"name_zh": "路易斯·布努埃尔", "category": "其他", "works": ["安达卢西亚犬"], "style": "超现实主义的荒诞与嘲弄", "keywords": ["超现实"]},
}


# ── 导演流派映射 (需求类型 → 推荐导演组合) ──
GENRE_DIRECTOR_MAP: dict[str, list[str]] = {
    "文艺剧情": ["wangkarwai-perspective", "houhsiaohsien-perspective", "hirokoreeda-perspective"],
    "悬疑惊悚": ["davidfincher-perspective", "christophernolan-perspective", "parkchanwook-perspective"],
    "动作商业": ["johnwoo-perspective", "tsuihark-perspective", "jamescameron-perspective"],
    "史诗历史": ["stevenspielberg-perspective", "franciscoppola-perspective", "zhangyimeng-perspective"],
    "黑色犯罪": ["johnnieto-perspective", "quentintarantino-perspective", "parkchanwook-perspective"],
    "超现实/梦境": ["andreitarkovsky-perspective", "federicofellini-perspective", "ingmarbergman-perspective"],
    "喜剧": ["stephenchow-perspective", "woodyallen-perspective", "jiangwen-perspective"],
    "动画/奇幻": ["hayaomiyazaki-perspective", "tsuihark-perspective", "christophernolan-perspective"],
    "科幻": ["christophernolan-perspective", "jamescameron-perspective", "akirakurosawa-perspective"],
    "纪录片/纪实": ["jiazhangke-perspective", "edwardyang-perspective", "ozuyasujiro-perspective"],
}


# ── 初始化: 加载所有 SKILL.md ────────────────────────────
def _load_all_directors() -> dict[str, DirectorStyle]:
    """从 director_styles/ 目录加载所有导演风格。"""
    base = Path(__file__).parent
    registry: dict[str, DirectorStyle] = {}

    for skill_dir in sorted(base.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        skill_id = skill_dir.name
        raw = skill_md.read_text(encoding="utf-8")

        meta = _DIRECTOR_META.get(skill_id, {})
        name_zh = meta.get("name_zh", skill_id.replace("-perspective", "").replace("-", " ").title())
        category = meta.get("category", "其他")
        core_style = meta.get("style", "")
        keywords = meta.get("keywords", [])
        works = meta.get("works", [])

        # 从 SKILL.md frontmatter 提取额外信息
        raw_meta: dict[str, Any] = {}
        frontmatter_match = re.match(r"^---\n(.*?)\n---", raw, re.DOTALL)
        if frontmatter_match:
            raw_meta = _parse_frontmatter(frontmatter_match.group(1))

        # 合并 name
        if not name_zh and "name" in raw_meta:
            fm_name = raw_meta["name"]
            name_zh = fm_name.replace("-", " ").title() if fm_name else name_zh

        director = DirectorStyle(
            id=skill_id,
            name_zh=name_zh,
            name_en=raw_meta.get("name_en", ""),
            category=category,
            core_style=core_style,
            keywords=keywords,
            representative_works=works,
            full_skill=raw,
            raw_metadata=raw_meta,
        )
        registry[skill_id] = director

    return registry


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 YAML frontmatter 为 dict。"""
    result: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            result[key] = val
    return result


# 初始化注册表
director_registry = _load_all_directors()


# ── 公开 API ──────────────────────────────────────────────

def list_directors(category: str | None = None) -> list:
    """列出所有（或按分类过滤）的导演。"""
    if category is None:
        return list(director_registry.values())
    return [d for d in director_registry.values() if d.category == category]


def get_director_style(director_id: str) -> DirectorStyle | None:
    """根据 ID 获取单个导演风格。支持中文名模糊匹配。"""
    if director_id in director_registry:
        return director_registry[director_id]
    # 按中文名模糊搜索
    for d in director_registry.values():
        if director_id in d.name_zh:
            return d
    return None


def match_directors_by_genre(genre: str) -> list[DirectorStyle]:
    """根据流派 / 需求类型匹配推荐导演。"""
    ids = GENRE_DIRECTOR_MAP.get(genre, [])
    return [director_registry[i] for i in ids if i in director_registry]


def build_collaboration_prompt(
    director_ids: list[str],
    mode: CollaborationMode = CollaborationMode.SEQUENTIAL,
    story_context: str = "",
) -> str:
    """构建多导演协作的 prompt 注入片段。

    Args:
        director_ids: 导演 ID 列表 (建议 1-5 位)
        mode: 协作模式
        story_context: 故事上下文描述

    Returns:
        一段可直接注入 system prompt 的导演风格描述。
    """
    styles = [director_registry[i] for i in director_ids if i in director_registry]
    if not styles:
        return ""

    parts = ["# 导演创作团风格注入\n"]
    parts.append(f"## 协作模式: {mode.value}\n")

    if story_context:
        parts.append(f"## 故事上下文\n{story_context}\n")

    if mode == CollaborationMode.SEQUENTIAL:
        parts.append("## 顺序链: 以下导演风格依次叠加，每位在前一位基础上深化\n")
    elif mode == CollaborationMode.DEBATE_VOTE:
        parts.append("## 辩论投票: 各位导演各自提出方案，取最优或融合\n")
    else:  # CHAIRMAN
        parts.append(f"## 主席团: {styles[0].name_zh} 主导，其他辅助提供备注\n")

    for i, s in enumerate(styles, 1):
        parts.append(f"\n### {i}. {s.name_zh}\n")
        parts.append(f"- **核心风格**: {s.core_style}")
        parts.append(f"- **关键词**: {', '.join(s.keywords) if s.keywords else '—'}")
        parts.append(f"- **代表作**: {', '.join(s.representative_works)}")

    parts.append("\n---")
    parts.append("请综合以上导演的美学风格与叙事特色，进行分镜创作。")

    return "\n".join(parts)


# ── 内部辅助 ─────────────────────────────────────────────────

def _parse_fromtmatter(text: str) -> dict[str, Any]:
    """已废弃，保留兼容。"""
    return {}


class DirectorStyleLoader:
    """导演风格加载器 — 兼容旧 API 的单例封装。"""

    @staticmethod
    def get(director_id: str) -> DirectorStyle | None:
        return get_director_style(director_id)

    @staticmethod
    def list_all(category: str | None = None) -> list[Dict]:
        return [vars(d) for d in list_directors(category) if d]

    @staticmethod
    @staticmethod
    def names() -> list[str]:
        return [d.name_zh for d in director_registry.values()]

    @staticmethod
    def by_genre(genre: str) -> list[str]:
        return [d.name_zh for d in match_directors_by_genre(genre)]

