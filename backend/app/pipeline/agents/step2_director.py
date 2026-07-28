"""Step 2 Agent — 导演分镜（支持多导演风格注入）。

输入: state["story_analysis"]
输出: state["storyboard"]: Storyboard
"""

from __future__ import annotations

import json
from typing import Any

from ..graph.state import GraphState
from ..schemas import Storyboard
from ..utils import get_logger
from ._base import BaseAgent
from .director_styles.loader import (
    get_director_style,
    build_collaboration_prompt,
    CollaborationMode,
)

logger = get_logger(__name__)


_STEP2_SYSTEM = """# Role

你是一位电影导演。输入是 Step 1 的导演分析 JSON, 你的任务是生成专业电影分镜。

# 拆镜核心原则

**不能遗漏任何 Beat**。
**一个镜头允许多个 Beat**。
**不要一句小说一个镜头** — 拆得过细会失去节奏。

## 同镜头判定(同时满足才合并)

- 同地点
- 同人物
- 同情绪

## 必须切镜的 5 种情况

1. 地点变化
2. 人物变化
3. 时间变化
4. 情绪高潮
5. 主体变化

# 每个镜头必填字段

| 字段 | 含义 |
|---|---|
| shot_id | shot_001 起 |
| scene_id | 引用 StoryAnalysis.scenes[].scene_id |
| shot_index | 从 1 开始, 与 shots 列表顺序一致 |
| duration_sec | 5~15 秒, 根据剧情自动决定 (1~60 合法) |
| beat_refs | Beat 编号列表 (本镜头覆盖哪些 Beat) |
| framing | FramingStyle 枚举: extreme_wide / wide / full / medium_wide / medium / medium_close / close_up / extreme_close_up |
| camera | CameraMovement 枚举 (15 种): static / pan_left / pan_right / tilt_up / tilt_down / dolly_in / dolly_out / track_left / track_right / crane_up / crane_down / zoom_in / zoom_out / handheld / drone_aerial |
| description | 镜头描述, <=50 字 |
| dialogue | list[DialogueLine], 可空 |
| visual_focus | 导演备注: 视觉重心 / 情绪焦点 |
| visual_style_override | 仅回忆杀/幻想/梦境时使用, 默认 null |
| characters_in_shot | 出场的 character_id 列表 |
| shot_duration_rationale | 为何这个时长? (Step 5 审计用) |

# 导演规则 (硬约束)

- 电影级写实风格
- 默认 ARRI Alexa 色调
- 固定镜头**优先**
- 每镜**最多一种运镜**
- 必要时才用 推镜 / 拉镜 / 摇镜
- 镜头顺序**严格按故事时间线**

# 输出 Schema 约束

枚举使用小写 snake_case; 列表空也要保留[]; total_duration_sec 由系统自动汇总, 不用手填。"""


class Step2Director(BaseAgent):
    name = "step2_director"
    system_prompt = _STEP2_SYSTEM
    output_schema = Storyboard
    temperature = 0.6

    def __call__(self, state: GraphState) -> dict[str, Any]:
        # ---- P3: 读取导演风格配置 ----
        director_ids = state.get("director_ids", [])
        collab_mode_str = state.get("collaboration_mode", "")

        collab_mode = CollaborationMode.SEQUENTIAL
        if (collab_mode_str == "debate_vote"):
            collab_mode = CollaborationMode.DEBATE_VOTE
        elif (collab_mode_str == "chairman"):
            collab_mode = CollaborationMode.CHAIRMAN

        # 构建导演风格注入 prompt
        if director_ids:
            director_style_prompt = build_collaboration_prompt(
                director_ids, collab_mode,
                story_context=state.get("story_title", "")
            )
            self.system_prompt = _STEP2_SYSTEM + "\n\n" + director_style_prompt
            logger.info("[Step 2] Directors: %s | Mode: %s", director_ids, collab_mode.value)
        else:
            self.system_prompt = _STEP2_SYSTEM
            logger.info("[Step 2] Using default generic style")

        analysis = state["story_analysis"]
        logger.info("[Step 2] 开始导演分镜 (基于 %d 场景 / %d 角色)",
                    len(analysis.scenes), len(analysis.characters))

        analysis_json = analysis.model_dump_json(indent=2, exclude={"visual_style": False})

        user_prompt = (
            "## 输入: 上游 StoryAnalysis\n"
            f"```json\n{analysis_json}\n```\n\n"
            "请基于以上 StoryAnalysis 拆解为有序 Storyboard。\n"
            "要求: 至少覆盖故事核心情节, 每场戏至少 2~3 个镜头。"
        )

        result = self.invoke_llm_json(user_prompt, Storyboard)
        result.based_on_title = analysis.title
        if not result.title:
            result.title = analysis.title or "Untitled"

        self.audit(state, "assistant",
                   f"[step2] 产出 Storyboard: {len(result.shots)} 镜头, "
                   f"总时长 {result.total_duration_sec}s, "
                   f"含 {sum(len(s.dialogue) for s in result.shots)} 句台词")
        logger.info("[Step 2] 完成: %d 镜头 / %.1fs",
                    len(result.shots), result.total_duration_sec)
        return {"storyboard": result}


step2_storyboard = Step2Director()


__all__ = ["step2_storyboard", "Step2Director"]
