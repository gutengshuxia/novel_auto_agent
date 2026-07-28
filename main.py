"""novel_codex_agent —— 入口脚本。

用法:
    python main.py data/sample_story.txt
    python main.py --title "女巫与龙" data/sample_story.txt

环境变量:
    OPENAI_API_KEY  —— 必填
    OPENAI_MODEL    —— 可选,默认 gpt-4o
    MAX_REPLAN_ROUNDS —— 可选,默认 3 (Step 5 回滚上限)
    OUTPUT_DIR      —— 可选,默认 ./output
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.pipeline.graph import build_graph
from backend.app.pipeline.graph.state import GraphState
from backend.app.pipeline.utils import export_prompts_to_excel, get_logger, CastManager, DEFAULT_CAST_FILE, StoryboardCardGenerator
from backend.app.pipeline.schemas import PromptPlan, Storyboard, StoryAnalysis

load_dotenv()
logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Story -> Multi-Version Video Prompt Pipeline"
    )
    parser.add_argument(
        "story_file",
        nargs="?",
        default="data/sample_story.txt",
        help="输入故事文本文件路径",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="故事标题(用于 Excel 命名)。默认取文件名。",
    )
    parser.add_argument(
        "--max-replans",
        type=int,
        default=int(os.getenv("MAX_REPLAN_ROUNDS", "3")),
        help="Step 5 一致性检查失败时的最大回滚次数",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("OUTPUT_DIR", "./output"),
        help="Excel 输出目录",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="自动接受所有 HITL 审核点 (CI / 批量处理用)",
    )
    parser.add_argument(
        "--no-hitl",
        action="store_true",
        help="跳过 HITL 审核节点 (完全自动, 与旧版兼容)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    story_path = Path(args.story_file)
    if not story_path.exists():
        logger.error("故事文件不存在: %s", story_path)
        return 1

    story_text = story_path.read_text(encoding="utf-8")
    title = args.title or story_path.stem

    # ---- 加载全局演员表 ----
    cast_manager = CastManager()
    cast_manager.load()

    initial_state: GraphState = {
        "story_text": story_text,
        "story_title": title,
        "max_replans": args.max_replans,
        "replan_count": 0,
        # 其余字段由各节点写入
        "story_analysis": None,
        "storyboard": None,
        "prompt_plan": None,
        "consistency_report": None,
        "final_outputs": None,
        "messages": [],
        # 全局演员表 (跨章节持久化)
        "cast_data": cast_manager.cast_data,
        "chapter_title": title,
    }

    logger.info("=== Pipeline 启动: %s ===", title)
    graph = build_graph()
    final_state = graph.invoke(initial_state)

    # P0 HITL 交互循环 (仅在非 auto-approve 且非 no-hitl 时启用)
    if not args.auto_approve and not args.no_hitl:
        while _has_pending_review(final_state):
            feedback = _prompt_user_review(final_state)
            if feedback == "quit":
                logger.warning("用户退出, 已生成部分产物")
                break
            final_state["human_feedback"].append(feedback)
            # 重新跑整个图 (LangGraph 会从 pending_review 节点恢复)
            final_state = graph.invoke(final_state)
            if final_state.get("pending_review") == "quit":
                break

    # Excel 导出 —— Step 4 已写过,这里再写一次最终版作为交付物
    storyboard: Storyboard | None = final_state.get("storyboard")
    prompt_plan: PromptPlan | None = final_state.get("prompt_plan")
    story_analysis: StoryAnalysis | None = final_state.get("story_analysis")
    director_ids: list[str] | None = final_state.get("director_ids")
    
    # 生成故事板分镜卡片
    storyboard_cards = []
    if storyboard and prompt_plan and story_analysis:
        try:
            card_generator = StoryboardCardGenerator(enable_image_generation=False)
            
            # 构建角色演员表
            character_sheets = {}
            cast_data = final_state.get("cast_data", {})
            for char in story_analysis.characters:
                char_sheet = (
                    cast_data.get(char.name, {}).get("character_sheet")
                    or char.character_sheet
                    or char.base_appearance
                    or ""
                )
                if char_sheet:
                    character_sheets[char.name] = char_sheet
            
            # 为每个镜头生成卡片
            for shot_prompt in prompt_plan.shot_prompts:
                # 获取场景描述
                scene_desc = ""
                if shot_prompt.shot_id in storyboard.shots:
                    shot = storyboard.shots[shot_prompt.shot_id]
                    scene_desc = shot.location or ""
                
                # 获取导演风格
                director_style = ""
                if director_ids:
                    director_style = ", ".join(director_ids)
                
                # 获取视频 prompt（取第一个 variant）
                video_prompt = ""
                if shot_prompt.variants:
                    video_prompt = shot_prompt.variants[0].prompt_text or ""
                
                if video_prompt:
                    cards = card_generator.generate_cards_from_prompt(
                        shot_id=shot_prompt.shot_id,
                        video_prompt=video_prompt,
                        character_sheets=character_sheets,
                        scene_description=scene_desc,
                        director_style=director_style,
                    )
                    storyboard_cards.extend(cards)
            
            logger.info("✅ 故事板卡片已生成: %d 张", len(storyboard_cards))
        except Exception as e:
            logger.error("故事板卡片生成失败: %s", e)
            import traceback
            traceback.print_exc()
    
    if storyboard and prompt_plan:
        xlsx = export_prompts_to_excel(
            storyboard=storyboard,
            prompt_plan=prompt_plan,
            output_dir=args.output_dir,
            story_title=title,
            story_analysis=story_analysis,
            director_ids=director_ids,
            cast_data=final_state.get("cast_data"),
            storyboard_cards=storyboard_cards,
        )
        logger.info("Excel 交付物: %s", xlsx)
    else:
        logger.warning("状态中缺少 storyboard 或 prompt_plan,跳过 Excel 导出。")

    # ---- 保存全局演员表 ----
    cast_manager.cast_data = final_state.get("cast_data", {})
    if cast_manager.cast_data:
        cast_manager._dirty = True  # 强制保存
        cast_manager.save()
    else:
        logger.warning("[CastManager] cast_data 为空, 跳过保存")

    logger.info("=== Pipeline 完成 ===")
    return 0


def _has_pending_review(state: GraphState) -> bool:
    """检查是否还有待审核节点。"""
    return state.get("pending_review") not in (None, "", "quit")


def _prompt_user_review(state: GraphState) -> str:
    """从 stdin 读取用户审核决策。"""
    print()
    print("=" * 60)
    print("👤 请审核当前产物 (输入 accept / modify:...=... / reject:... / quit):")
    print("=" * 60)
    return input("> ").strip()


if __name__ == "__main__":
    sys.exit(main())
