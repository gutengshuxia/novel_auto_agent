"""完整 Prompt Pipeline 任务：Beat 规划 → 时间戳 Prompt → 一致性审计 → 模型适配。

整合 Pipeline Step 3-6 的完整流程，适配 Jellyfish DB 数据。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chains.agents import (
    BeatPlanningAgent,
    ModelAdapterAgent,
    PromptConsistencyAgent,
    TimestampPromptAgent,
)
from app.core.db import async_session_maker
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import TaskStatus
from app.models.studio import (
    Chapter,
    Character,
    Costume,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Prop,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDetail,
)
from app.services.film.shot_frame_prompt_tasks import (
    _build_character_context,
    _build_continuity_guidance,
    _build_director_command_summary,
    _build_named_asset_context,
    _build_subject_priority,
    _build_composition_anchor,
    _build_screen_direction_guidance,
    _build_frame_specific_guidance,
    _enum_value,
    _compact_text,
    _same_scene,
)
from app.services.llm.runtime import build_default_text_llm_sync
from app.services.worker.task_logging import log_task_event, log_task_failure
from app.services.worker.async_task_support import cancel_if_requested_async
from app.services.studio.shot_status import recompute_shot_status

logger = logging.getLogger(__name__)


async def _load_shot_context(db: AsyncSession, shot_id: str) -> dict[str, Any]:
    """加载镜头完整上下文（复用 shot_frame_prompt_tasks 的逻辑）。"""
    shot_stmt = (
        select(Shot)
        .options(
            selectinload(Shot.detail).selectinload(ShotDetail.dialog_lines),
            selectinload(Shot.detail).selectinload(ShotDetail.scene),
            selectinload(Shot.chapter).selectinload(Chapter.project),
            selectinload(Shot.character_links)
            .selectinload(ShotCharacterLink.character)
            .selectinload(Character.actor),
            selectinload(Shot.character_links)
            .selectinload(ShotCharacterLink.character)
            .selectinload(Character.costume),
            selectinload(Shot.scene_links).selectinload(ProjectSceneLink.scene),
            selectinload(Shot.prop_links).selectinload(ProjectPropLink.prop),
            selectinload(Shot.costume_links).selectinload(ProjectCostumeLink.costume),
        )
        .where(Shot.id == shot_id)
    )
    shot = (await db.execute(shot_stmt)).scalar_one_or_none()
    if shot is None:
        raise RuntimeError(f"Shot not found: {shot_id}")
    if shot.detail is None:
        raise RuntimeError(f"ShotDetail not found: {shot_id}")

    detail = shot.detail

    # 相邻镜头
    neighbors_stmt = (
        select(Shot)
        .options(selectinload(Shot.detail).selectinload(ShotDetail.scene))
        .where(
            Shot.chapter_id == shot.chapter_id,
            Shot.index.in_([shot.index - 1, shot.index + 1]),
        )
    )
    neighbor_rows = (await db.execute(neighbors_stmt)).scalars().all()
    previous_shot = next((s for s in neighbor_rows if s.index == shot.index - 1), None)
    next_shot = next((s for s in neighbor_rows if s.index == shot.index + 1), None)

    # 实体
    characters = [
        link.character
        for link in sorted(list(getattr(shot, "character_links", []) or []), key=lambda item: (item.index, item.id))
        if getattr(link, "character", None) is not None
    ]
    scenes_by_id: dict[str, Scene] = {}
    detail_scene = getattr(detail, "scene", None)
    if detail_scene is not None:
        scenes_by_id[str(detail_scene.id)] = detail_scene
    for link in list(getattr(shot, "scene_links", []) or []):
        scene = getattr(link, "scene", None)
        if scene is not None:
            scenes_by_id[str(scene.id)] = scene
    props = [link.prop for link in list(getattr(shot, "prop_links", []) or []) if getattr(link, "prop", None) is not None]
    costumes = [link.costume for link in list(getattr(shot, "costume_links", []) or []) if getattr(link, "costume", None) is not None]
    scenes = list(scenes_by_id.values())

    dialog_summary = "\n".join(line.text for line in (detail.dialog_lines or []) if line.text)

    # 相邻镜头摘要
    def _neighbor_summary(s):
        if s is None:
            return "", "", ""
        d = getattr(s, "detail", None)
        return (
            _compact_text(getattr(s, "title", None)),
            _compact_text(getattr(s, "script_excerpt", None))[:80],
            _compact_text(getattr(d, "description", None))[:80] if d else "",
        )

    prev_title, prev_excerpt, prev_state = _neighbor_summary(previous_shot)
    next_title, next_excerpt, next_goal = _neighbor_summary(next_shot)

    # 上下文构建
    character_context = _build_character_context(characters)
    scene_context = _build_named_asset_context(scenes)
    prop_context = _build_named_asset_context(props)
    costume_context = _build_named_asset_context(costumes)

    continuity_guidance = _build_continuity_guidance(
        previous_shot=previous_shot, current_shot=shot, next_shot=next_shot,
    )
    composition_anchor = _build_composition_anchor(
        detail=detail, previous_shot=previous_shot, next_shot=next_shot,
        characters=characters, scenes=scenes,
    )
    screen_direction_guidance = _build_screen_direction_guidance(
        detail=detail, previous_shot=previous_shot, next_shot=next_shot,
        dialogue_summary=dialog_summary,
        character_names=[c.name for c in characters],
    )
    frame_specific_guidance = _build_frame_specific_guidance(
        frame_type="key", previous_shot=previous_shot, next_shot=next_shot,
        detail=detail, script_excerpt=shot.script_excerpt or "",
        action_beats=[str(b) for b in (detail.action_beats or [])],
    )
    director_command = _build_director_command_summary(
        frame_type="key",
        frame_specific_guidance=frame_specific_guidance,
        continuity_guidance=continuity_guidance,
        composition_anchor=composition_anchor,
        screen_direction_guidance=screen_direction_guidance,
        has_dialogue=bool(dialog_summary.strip()),
        character_count=len(characters),
        same_scene_with_previous=_same_scene(previous_shot, str(detail.scene_id or "")),
        same_scene_with_next=_same_scene(next_shot, str(detail.scene_id or "")),
        movement=_enum_value(detail.movement),
    )

    return {
        "shot": shot,
        "detail": detail,
        "characters": characters,
        "dialog_summary": dialog_summary,
        "character_context": character_context,
        "scene_context": scene_context,
        "prop_context": prop_context,
        "costume_context": costume_context,
        "previous_shot_title": prev_title,
        "previous_shot_end_state": prev_state,
        "next_shot_title": next_title,
        "next_shot_start_goal": next_goal,
        "director_command_summary": director_command,
        "character_names": [c.name for c in characters],
    }


async def run_full_prompt_pipeline(
    task_id: str,
    run_args: dict,
) -> None:
    """完整 Prompt Pipeline：Beat → Timestamp → Consistency → Model Adapt。"""
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 5)
            await session.commit()
            log_task_event("full_prompt_pipeline", task_id, "running")

            shot_id = str(run_args.get("shot_id") or "")
            target_model = str(run_args.get("target_model") or "通用")
            if not shot_id:
                raise RuntimeError("Missing shot_id")

            # 加载上下文
            log_task_event("full_prompt_pipeline", task_id, "running", step="加载镜头上下文")
            ctx = await _load_shot_context(session, shot_id)
            detail = ctx["detail"]
            shot = ctx["shot"]

            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                return

            # Step 1: Beat 规划
            log_task_event("full_prompt_pipeline", task_id, "running", step="Beat 规划")
            await store.set_progress(task_id, 15)
            await session.commit()

            llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=True))
            beat_agent = BeatPlanningAgent(llm)
            beat_result = await beat_agent.aextract(
                script_excerpt=shot.script_excerpt or "",
                title=shot.title or "",
                shot_description=detail.description or "",
                camera_shot=_enum_value(detail.camera_shot),
                angle=_enum_value(detail.angle),
                movement=_enum_value(detail.movement),
                atmosphere=detail.atmosphere or "",
                mood_tags=detail.mood_tags or [],
                duration=detail.duration,
                dialog_summary=ctx["dialog_summary"],
                character_context=ctx["character_context"],
                scene_context=ctx["scene_context"],
                prop_context=ctx["prop_context"],
                costume_context=ctx["costume_context"],
            )
            beat_count = len(beat_result.beats)
            log_task_event("full_prompt_pipeline", task_id, "running",
                          step=f"Beat 规划完成：{beat_count} 个 Beat")

            # 格式化 Beat 序列为文本
            beat_text_lines = []
            for b in beat_result.beats:
                line = f"[{b.start_time}-{b.end_time}s] {b.action}"
                if b.character:
                    line += f"（{b.character}）"
                if b.micro_expression:
                    line += f" 微表情：{b.micro_expression}"
                if b.body_language:
                    line += f" 肢体：{b.body_language}"
                if b.dialogue:
                    line += f" 对白：{b.dialogue}"
                beat_text_lines.append(line)
            beat_sequence = "\n".join(beat_text_lines)

            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                return

            # Step 2: 时间戳 Prompt 生成
            log_task_event("full_prompt_pipeline", task_id, "running", step="生成时间戳 Prompt")
            await store.set_progress(task_id, 40)
            await session.commit()

            from app.chains.agents.timestamp_prompt_agent import MODEL_STYLE_GUIDE
            style_guide = MODEL_STYLE_GUIDE.get(target_model.lower(), "使用通用高质量视频 Prompt 风格")
            char_names_at = "、".join(f"@{name}" for name in ctx["character_names"]) if ctx["character_names"] else "无"

            prompt_agent = TimestampPromptAgent(llm)
            prompt_result = await prompt_agent.aextract(
                target_model=target_model,
                style_guide=style_guide,
                character_names_at=char_names_at,
                script_excerpt=shot.script_excerpt or "",
                title=shot.title or "",
                camera_shot=_enum_value(detail.camera_shot),
                angle=_enum_value(detail.angle),
                movement=_enum_value(detail.movement),
                atmosphere=detail.atmosphere or "",
                duration=detail.duration,
                beat_sequence=beat_sequence,
                sound_design=beat_result.sound_design,
                subject_analysis=beat_result.subject_analysis,
                character_context=ctx["character_context"],
                scene_context=ctx["scene_context"],
                prop_context=ctx["prop_context"],
                costume_context=ctx["costume_context"],
                previous_shot_title=ctx["previous_shot_title"],
                previous_shot_end_state=ctx["previous_shot_end_state"],
                next_shot_title=ctx["next_shot_title"],
                next_shot_start_goal=ctx["next_shot_start_goal"],
                director_command_summary=ctx["director_command_summary"],
            )
            log_task_event("full_prompt_pipeline", task_id, "running",
                          step=f"Prompt 生成完成：{len(prompt_result.prompt_text)} 字符")

            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                return

            # Step 3: 一致性审计
            log_task_event("full_prompt_pipeline", task_id, "running", step="一致性审计")
            await store.set_progress(task_id, 65)
            await session.commit()

            audit_llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=False))
            audit_agent = PromptConsistencyAgent(audit_llm)
            audit_result = await audit_agent.aextract(
                character_context=ctx["character_context"],
                scene_context=ctx["scene_context"],
                prop_context=ctx["prop_context"],
                costume_context=ctx["costume_context"],
                script_excerpt=shot.script_excerpt or "",
                title=shot.title or "",
                camera_shot=_enum_value(detail.camera_shot),
                angle=_enum_value(detail.angle),
                movement=_enum_value(detail.movement),
                atmosphere=detail.atmosphere or "",
                duration=detail.duration,
                previous_shot_title=ctx["previous_shot_title"],
                previous_shot_end_state=ctx["previous_shot_end_state"],
                next_shot_title=ctx["next_shot_title"],
                next_shot_start_goal=ctx["next_shot_start_goal"],
                prompt_text=prompt_result.prompt_text,
                negative_prompt=prompt_result.negative_prompt,
            )
            log_task_event("full_prompt_pipeline", task_id, "running",
                          step=f"审计完成：score={audit_result.overall_score} passed={audit_result.passed}")

            # 如果审计未通过且有优化建议，使用优化后的 Prompt
            final_prompt = prompt_result.prompt_text
            final_negative = prompt_result.negative_prompt
            if not audit_result.passed and audit_result.optimized_prompt:
                final_prompt = audit_result.optimized_prompt
                log_task_event("full_prompt_pipeline", task_id, "running",
                              step="审计未通过，使用优化后的 Prompt")

            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                return

            # Step 4: 模型适配
            log_task_event("full_prompt_pipeline", task_id, "running", step=f"模型适配：{target_model}")
            await store.set_progress(task_id, 85)
            await session.commit()

            adapt_agent = ModelAdapterAgent()
            adapt_result = adapt_agent.extract(
                prompt_text=final_prompt,
                target_model=target_model,
                camera=_enum_value(detail.movement),
                negative_prompt=final_negative,
            )
            log_task_event("full_prompt_pipeline", task_id, "running",
                          step=f"模型适配完成：{adapt_result.notes}")

            # 写入 DB
            shot_detail = await session.get(ShotDetail, shot_id)
            if shot_detail is None:
                raise RuntimeError(f"ShotDetail not found: {shot_id}")

            shot_detail.first_frame_prompt = adapt_result.prompt_text
            shot_detail.key_frame_prompt = adapt_result.prompt_text
            shot_detail.last_frame_prompt = adapt_result.prompt_text

            result_payload = {
                "prompt_text": adapt_result.prompt_text,
                "negative_prompt": adapt_result.negative_prompt,
                "target_model": target_model,
                "beat_count": beat_count,
                "audit_score": audit_result.overall_score,
                "audit_passed": audit_result.passed,
                "audit_issues": audit_result.issues,
                "retry_count": retry_count,
                "adapt_notes": adapt_result.notes,
                "subject_analysis": beat_result.subject_analysis,
                "sound_design": beat_result.sound_design,
            }
            await store.set_result(task_id, result_payload)

            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                return

            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
            log_task_event("full_prompt_pipeline", task_id, "succeeded",
                          step=f"Pipeline 完成：score={audit_result.overall_score}")

        except Exception as exc:
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                shot_id = str(run_args.get("shot_id") or "")
                if shot_id:
                    await recompute_shot_status(s2, shot_id=shot_id)
                await s2.commit()
            log_task_failure("full_prompt_pipeline", task_id, str(exc))


# ---- ?? Pipeline ----


async def run_batch_pipeline(task_id: str, run_args: dict[str, Any]) -> None:
    """???????????????? Pipeline?

    run_args:
        chapter_id: str  -- ?? ID
        target_model: str -- ????
    """
    chapter_id = run_args.get("chapter_id")
    target_model = run_args.get("target_model", "??")

    async with async_session_maker() as session:
        store = SqlAlchemyTaskStore(session)
        try:
            log_task_event("batch_pipeline", task_id, "running", step=f"???? Pipeline???={chapter_id} ??={target_model}")

            # ????????
            shot_stmt = (
                select(Shot)
                .options(selectinload(Shot.detail))
                .where(Shot.chapter_id == chapter_id)
                .order_by(Shot.index)
            )
            shots = (await session.execute(shot_stmt)).scalars().all()

            if not shots:
                await store.set_status(task_id, TaskStatus.failed)
                await store.set_error(task_id, f"?? {chapter_id} ????")
                await session.commit()
                return

            total = len(shots)
            log_task_event("batch_pipeline", task_id, "running", step=f"? {total} ??????")
            await store.set_progress(task_id, 5)
            await session.commit()

            results: list[dict[str, Any]] = []
            for idx, shot in enumerate(shots):
                if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                    return

                shot_id = str(shot.id)
                progress = 5 + int(90 * (idx + 1) / total)
                await store.set_progress(task_id, progress)
                log_task_event("batch_pipeline", task_id, "running",
                              step=f"???? {idx + 1}/{total}?{shot.title or shot_id}")

                # ????????? Pipeline
                try:
                    await _run_single_pipeline_core(
                        task_id=task_id,
                        shot_id=shot_id,
                        target_model=target_model,
                        store=store,
                        session=session,
                    )
                    results.append({"shot_id": shot_id, "status": "succeeded"})
                except Exception as e:
                    results.append({"shot_id": shot_id, "status": "failed", "error": str(e)})
                    log_task_event("batch_pipeline", task_id, "running",
                                  step=f"?? {shot_id} ???{e}")

            succeeded = sum(1 for r in results if r["status"] == "succeeded")
            failed = sum(1 for r in results if r["status"] == "failed")

            await store.set_progress(task_id, 100)
            await store.set_result(task_id, {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "results": results,
                "target_model": target_model,
                "chapter_id": chapter_id,
            })
            await store.set_status(task_id, TaskStatus.succeeded)
            await session.commit()
            log_task_event("batch_pipeline", task_id, "succeeded",
                          step=f"?? Pipeline ???{succeeded}/{total} ??")

        except Exception as exc:
            await session.rollback()
            async with async_session_maker() as s2:
                store2 = SqlAlchemyTaskStore(s2)
                await store2.set_error(task_id, str(exc))
                await store2.set_status(task_id, TaskStatus.failed)
                await s2.commit()
            log_task_failure("batch_pipeline", task_id, str(exc))


async def _run_single_pipeline_core(
    task_id: str,
    shot_id: str,
    target_model: str,
    store: SqlAlchemyTaskStore,
    session: AsyncSession,
) -> None:
    """????????? Pipeline ??????????????"""
    from app.chains.agents.timestamp_prompt_agent import MODEL_STYLE_GUIDE

    ctx = await _load_shot_context(session, shot_id)
    shot_stmt = (
        select(Shot)
        .options(selectinload(Shot.detail))
        .where(Shot.id == shot_id)
    )
    shot = (await session.execute(shot_stmt)).scalar_one_or_none()
    if shot is None or shot.detail is None:
        raise RuntimeError(f"Shot not found: {shot_id}")
    detail = shot.detail

    llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=False))

    # Step 1: Beat ??
    planner = BeatPlanningAgent(llm)
    beat_result = await planner.aextract(
        script_excerpt=shot.script_excerpt or "",
        title=shot.title or "",
        camera_shot=_enum_value(detail.camera_shot),
        angle=_enum_value(detail.angle),
        movement=_enum_value(detail.movement),
        atmosphere=detail.atmosphere or "",
        duration=detail.duration,
        character_context=ctx["character_context"],
        scene_context=ctx["scene_context"],
        prop_context=ctx["prop_context"],
        costume_context=ctx["costume_context"],
    )
    beat_count = len(beat_result.beats)

    # Format beat sequence
    beat_text_lines = []
    for b in beat_result.beats:
        line = f"[{b.start_time}-{b.end_time}s] {b.action}"
        if b.character:
            line += f"?{b.character}?"
        beat_text_lines.append(line)
    beat_sequence = "\n".join(beat_text_lines)

    # Step 2: Timestamp Prompt
    style_guide = MODEL_STYLE_GUIDE.get(target_model.lower(), "????????? Prompt ??")
    char_names_at = "?".join(f"@{name}" for name in ctx["character_names"]) if ctx["character_names"] else "?"

    prompt_agent = TimestampPromptAgent(llm)
    prompt_result = await prompt_agent.aextract(
        target_model=target_model,
        style_guide=style_guide,
        character_names_at=char_names_at,
        script_excerpt=shot.script_excerpt or "",
        title=shot.title or "",
        camera_shot=_enum_value(detail.camera_shot),
        angle=_enum_value(detail.angle),
        movement=_enum_value(detail.movement),
        atmosphere=detail.atmosphere or "",
        duration=detail.duration,
        beat_sequence=beat_sequence,
        sound_design=beat_result.sound_design,
        subject_analysis=beat_result.subject_analysis,
        character_context=ctx["character_context"],
        scene_context=ctx["scene_context"],
        prop_context=ctx["prop_context"],
        costume_context=ctx["costume_context"],
        previous_shot_title=ctx["previous_shot_title"],
        previous_shot_end_state=ctx["previous_shot_end_state"],
        next_shot_title=ctx["next_shot_title"],
        next_shot_start_goal=ctx["next_shot_start_goal"],
        director_command_summary=ctx["director_command_summary"],
    )

    # Step 3: Consistency Audit
    audit_llm = await session.run_sync(lambda sync_db: build_default_text_llm_sync(sync_db, thinking=False))
    audit_agent = PromptConsistencyAgent(audit_llm)
    audit_result = await audit_agent.aextract(
        character_context=ctx["character_context"],
        scene_context=ctx["scene_context"],
        prop_context=ctx["prop_context"],
        costume_context=ctx["costume_context"],
        script_excerpt=shot.script_excerpt or "",
        title=shot.title or "",
        camera_shot=_enum_value(detail.camera_shot),
        angle=_enum_value(detail.angle),
        movement=_enum_value(detail.movement),
        atmosphere=detail.atmosphere or "",
        duration=detail.duration,
        previous_shot_title=ctx["previous_shot_title"],
        previous_shot_end_state=ctx["previous_shot_end_state"],
        next_shot_title=ctx["next_shot_title"],
        next_shot_start_goal=ctx["next_shot_start_goal"],
        prompt_text=prompt_result.prompt_text,
        negative_prompt=prompt_result.negative_prompt,
    )

    final_prompt = prompt_result.prompt_text
    final_negative = prompt_result.negative_prompt
    if not audit_result.passed and audit_result.optimized_prompt:
        final_prompt = audit_result.optimized_prompt

    # Step 4: Model Adaptation
    adapt_agent = ModelAdapterAgent()
    adapt_result = adapt_agent.extract(
        prompt_text=final_prompt,
        target_model=target_model,
        camera=_enum_value(detail.movement),
        negative_prompt=final_negative,
    )

    # Write to DB
    shot_detail = await session.get(ShotDetail, shot_id)
    if shot_detail is None:
        raise RuntimeError(f"ShotDetail not found: {shot_id}")

    shot_detail.first_frame_prompt = adapt_result.prompt_text
    shot_detail.key_frame_prompt = adapt_result.prompt_text
    shot_detail.last_frame_prompt = adapt_result.prompt_text

    await recompute_shot_status(session, shot_id=shot_id)
    await session.commit()
