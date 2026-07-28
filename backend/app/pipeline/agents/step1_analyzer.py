"""Step 1 Agent —— 剧本分析。

输入: state["story_text"]
输出: state["story_analysis"]: StoryAnalysis
"""

from __future__ import annotations

from typing import Any

from ..graph.state import GraphState
from ..schemas import StoryAnalysis
from ..utils import get_logger
from ._base import BaseAgent

logger = get_logger(__name__)


_STEP1_SYSTEM = """# Role

你是一位拥有 20 年以上经验的电影导演、编剧、摄影指导 (DPO)。
你的任务**不是**生成 Prompt, 而是分析小说。所有分析都必须站在导演角度。

# 工作目标

阅读小说, 理解: 剧情 / 人物 / 情绪 / 节奏 / 镜头价值。
不要生成任何 Prompt。

# 分析流程

## Step 1 — 全文阅读
建立全景认知。

## Step 2 — 提取核心要素
- 故事背景 / 时间 / 地点
- 人物与人物关系
- 故事目标 / 故事冲突

## Step 3 — 拆分剧情 Beat
Beat = 一个完整戏剧动作 (例: 抽烟 → 吐烟 → 抓头 → 骂人 → 拿手机 → 打开微信 ...)。
**禁止遗漏任何 Beat**。

## Step 4 — 分析每个 Beat
对每个 Beat 输出:
- 动作 / 人物 / 情绪 / 对白 / 环境 / 重要程度 / 是否属于高潮

## Step 5 — 分析电影节奏
对每个 Beat 标记:
- 慢 / 快 / 停顿 / 留白 / 长镜头 / 短镜头

## Step 6 — 分析镜头价值
标记哪些 Beat 适合: 固定 / 推镜 / 拉镜 / 摇镜 / 跟拍。

## Step 7 — 锁定角色基准形象 (P1, 关键!)

对每个角色, 在 characters[].visual_anchor 字段写入**详细基准形象描述**:

必须包含:
- 面部特征: 脸型 / 五官 / 眉眼 / 唇形 / 肤色
- 发型发饰: 发色 / 发型 / 标志性发饰
- 服装款式: 风格 / 颜色 / 配饰
- 标志性道具: 武器 / 饰品 / 随身物品
- 整体气质: 气场 / 表情 / 姿态

**目的**: 防止后续 Step 4 在多镜头生成中让角色“变脸”。

## Step 8 — 生成演员表 (character_sheet, 关键!)

对每个角色, 在 character_sheet 字段写入完整的「演员表级描述」(>=150 字符):

结构:
1. 主视觉区: 正面+侧面+背面整体身形/服饰/标志性特征
2. 面部特写: 脸型/眉眼/鼻梁/唇形/肤色(明确色值如“冷白皮”/“小麦色”)
3. 配色板: 发色/服装主色/配饰色的具体色值描述
4. 局部细节: 关键配饰/道具/身份识别元素
5. 全身比例: 身高体型参考(如“身高约178cm，肩宽体瘦”)
6. 气质风格: 整体气场/表情基调/姿态习惯

示例:
"年龄约20岁，身高约178cm，身形清瘦。面部: 棱角分明的窄脸，颛骨微高，
肤色苍白(冷白皮)，深褐色眼睛眼尾微垂带疲惫感，眉骨下压，鼻梁挺直，
嘴唇薄而抿紧。发型: 黑色短发略显凌乱，额前有几缕碎发。
服装: 洗得发白的深蓝色连帽卫衣+黑色薄款夹克+深灰色牛仔裤+白色运动鞋。
配饰: 无。道具: 口袋中常备揉皱的医院催款单。
气质: 隐忍克制，下颌常绷紧，站姿微微前倾像随时准备行动。"

**重要**: character_sheet 是 Step 4 生成 Prompt 时的「演员表」参考，
首次出现的角色会完整引用此描述，后续镜头用 @角色名 简写引用。


# 输出 Schema 约束 (Pydantic)

输出 JSON 字段 (严格匹配, 不可省略, 不可新增顶层字段):

| 字段 | 类型 | 约束 |
|---|---|---|
| title | string | 故事标题, 原文未给可空 |
| genre | string | 题材, 如 奇幻 / 悬疑 |
| tone | enum | MoodTone: dark/hopeful/tense/mysterious/epic/whimsical/melancholic/romantic/horror/neutral |
| visual_style | enum | VisualStyle: cinematic/anime/realistic/oil_painting/watercolor/pixel_art/noir/cyberpunk/fantasy/documentary |
| target_models | enum[] | 从 TargetModel 5 选 N: runway/kling/jimeng/veo/pixverse |
| characters | object[] | **≥1 个**, 每项含 character_id / name / role / appearance / personality / visual_keywords / visual_anchor / **character_sheet** (>=150 字符) / reference_image_url |
| scenes | object[] | **≥1 个**, 每项含 scene_id (scene_001 起) / location / time_of_day / description (**≥10 字**) / characters (引用的 character_id 列表) / visual_keywords |
| plot_summary | string | **≥20 字**, 概括主线 |
| visual_keywords | string[] | 全局视觉关键词, 用于 Step 2 拆镜参考 |

# 跨字段硬约束 (LLM 必须自行校验, 否则 Pydantic 会拒)

- scenes[].characters 引用的 character_id 必须先在 characters[].character_id 中声明
- 枚举值使用小写 snake_case (MoodTone=cinematic, VisualStyle=cinematic 等)
- 列表字段即使为空也要保留为 []"""


class Step1Analyzer(BaseAgent):
    name = "step1_analyzer"
    system_prompt = _STEP1_SYSTEM
    output_schema = StoryAnalysis
    temperature = 0.5

    def __call__(self, state: GraphState) -> dict[str, Any]:
        story_text = state["story_text"]
        story_title = state.get("story_title", "")
        logger.info("[Step 1] 开始剧本分析 (输入 %d 字)", len(story_text))

        user_prompt = (
            f"## 故事标题 (可能为空)\n{story_title or '(无)'}\n\n"
            f"## 故事原文\n```\n{story_text}\n```\n\n"
            "请严格按 JSON Schema 输出 StoryAnalysis。"
        )

        result = self.invoke_llm_json(user_prompt, StoryAnalysis)
        # title 兜底
        if not result.title:
            result.title = story_title or "Untitled"

        # ---- 演员表兜底: 若 character_sheet 为空或过短, 用 visual_anchor + appearance 拼接 ----
        for ch in result.characters:
            if not ch.character_sheet or len(ch.character_sheet) < 100:
                parts = []
                if ch.visual_anchor:
                    parts.append(ch.visual_anchor)
                if ch.appearance:
                    parts.append(ch.appearance)
                if ch.personality:
                    parts.append(f"气质: {ch.personality}")
                ch.character_sheet = "。".join(parts) if parts else ""
                if ch.character_sheet:
                    logger.warning(
                        "[Step 1] 角色 %s 的 character_sheet 不足, 已用 visual_anchor+appearance 兜底",
                        ch.name,
                    )

        # ---- P3: 自动构建 asset_registry ----
        from ..schemas import AssetNode, AssetRegistry, AssetType, AssetSource
        registry = AssetRegistry()
        for ch in result.characters:
            registry.register(AssetNode(
                node_key=ch.character_id,
                asset_type=AssetType.CHARACTER,
                source=AssetSource.USER_UPLOAD if ch.reference_image_url else AssetSource.LLM_INFERRED,
                reference_url=ch.reference_image_url,
                description=ch.visual_anchor or ch.appearance,
                bound_to=ch.character_id,
                priority=100 if ch.reference_image_url else 10,
            ))
        for sc in result.scenes:
            registry.register(AssetNode(
                node_key=sc.scene_id,
                asset_type=AssetType.SCENE,
                source=AssetSource.LLM_INFERRED,
                reference_url="",
                description=sc.description,
                bound_to=sc.scene_id,
                priority=10,
            ))

        self.audit(state, "assistant",
                   f"[step1] 产出 StoryAnalysis: {len(result.characters)} 角色, "
                   f"{len(result.scenes)} 场景, "
                   f"资产={len(registry.nodes)} 个; "
                   f"目标模型={result.target_models}")
        logger.info("[Step 1] ✅ 完成: %d 角色 / %d 场景 / %d 资产",
                    len(result.characters), len(result.scenes), len(registry.nodes))

        # ---- 合并角色到全局演员表 (跨章节持久化) ----
        cast_data = state.get("cast_data") or {}
        chapter_title = state.get("chapter_title") or story_title or "unknown"
        if cast_data is not None:
            from ..utils import CastManager
            temp_cm = CastManager.__new__(CastManager)
            temp_cm.cast_data = cast_data
            temp_cm._dirty = False
            merge_result = temp_cm.merge_characters(
                [ch.model_dump() for ch in result.characters],
                chapter_title,
            )
            cast_data = temp_cm.cast_data
            if merge_result["new"]:
                logger.info("[Step 1] ✨ 新角色注册: %s", merge_result["new"])
            if merge_result["updated"]:
                logger.info("[Step 1] 🔄 角色更新: %s", merge_result["updated"])

        return {
            "story_analysis": result,
            "asset_registry": registry,
            "cast_data": cast_data,
        }


step1_analyze = Step1Analyzer()


__all__ = ["step1_analyze", "Step1Analyzer"]
