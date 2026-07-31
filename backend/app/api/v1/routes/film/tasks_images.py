from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.dependencies import get_db
from app.models.task_links import GenerationTaskLink
from app.schemas.common import ApiResponse, created_response
from app.services.film.shot_frame_prompt_tasks import (
    build_run_args as build_shot_frame_prompt_run_args,
    normalize_frame_type,
    relation_type_for_frame,
)
from app.services.studio.shot_status import mark_shot_generating
from app.tasks.execute_task import enqueue_task_execution

from .common import (
    ShotFramePromptRequest,
    TaskCreated,
    _CreateOnlyTask,
)
router = APIRouter()


@router.post(
    "/tasks/shot-frame-prompts",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="镜头分镜帧提示词生成（任务版）",
)
async def create_shot_frame_prompt_task(
    body: ShotFramePromptRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    frame_type = normalize_frame_type(body.frame_type)
    relation_type = relation_type_for_frame(frame_type)

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    run_args = await build_shot_frame_prompt_run_args(
        db,
        shot_id=body.shot_id,
        frame_type=frame_type,
    )

    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind="shot_frame_prompt",
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="prompt",
            relation_type=relation_type,
            relation_entity_id=body.shot_id,
        )
    )
    await mark_shot_generating(db, shot_id=body.shot_id)
    await db.commit()

    enqueue_task_execution(task_record.id)
    return created_response(TaskCreated(task_id=task_record.id))


# ---- Full Prompt Pipeline ----

from pydantic import BaseModel, Field

class FullPromptPipelineRequest(BaseModel):
    shot_id: str = Field(..., description="镜头 ID")
    target_model: str = Field("通用", description="目标模型：kling/jimeng/veo/runway/pixverse/通用")


@router.post(
    "/tasks/full-prompt-pipeline",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="完整 Prompt Pipeline（Beat规划→时间戳Prompt→一致性审计→模型适配）",
)
async def create_full_prompt_pipeline_task(
    body: FullPromptPipelineRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    from app.services.film.full_prompt_pipeline_tasks import _load_shot_context

    # 构建 run_args
    ctx = await _load_shot_context(db, body.shot_id)
    run_args = {
        "shot_id": body.shot_id,
        "target_model": body.target_model,
    }

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind="full_prompt_pipeline",
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="prompt",
            relation_type="full_prompt_pipeline",
            relation_entity_id=body.shot_id,
        )
    )
    await mark_shot_generating(db, shot_id=body.shot_id)
    await db.commit()

    enqueue_task_execution(task_record.id)
    return created_response(TaskCreated(task_id=task_record.id))



# ---- ?? Full Prompt Pipeline ----

class BatchFullPromptPipelineRequest(BaseModel):
    chapter_id: str = Field(..., description="?? ID")
    target_model: str = Field("??", description="?????kling/jimeng/veo/runway/pixverse/sora/hailuo/??")


@router.post(
    "/tasks/batch-full-prompt-pipeline",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="???? Prompt Pipeline???????????????",
)
async def create_batch_full_prompt_pipeline_task(
    body: BatchFullPromptPipelineRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    run_args = {
        "chapter_id": body.chapter_id,
        "target_model": body.target_model,
    }

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        task_kind="batch_pipeline",
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="prompt",
            relation_type="batch_pipeline",
            relation_entity_id=body.chapter_id,
        )
    )
    await db.commit()

    enqueue_task_execution(task_record.id)
    return created_response(TaskCreated(task_id=task_record.id))


# ---- Excel ?? ----

from fastapi.responses import StreamingResponse
import io
import json

@router.get(
    "/tasks/{task_id}/export-excel",
    summary="?? Pipeline ??? Excel",
)
async def export_pipeline_excel(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """?? Pipeline ??? Excel ???"""
    try:
        import openpyxl
    except ImportError:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="openpyxl not installed")

    store = SqlAlchemyTaskStore(db)
    task = await store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = task.result or {}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pipeline ??"

    # ??
    headers = ["??", "?"]
    ws.append(headers)

    # ????
    rows = [
        ("????", result.get("target_model", "")),
        ("Beat ??", result.get("beat_count", "")),
        ("????", result.get("audit_score", "")),
        ("????", "?" if result.get("audit_passed") else "?"),
        ("????", result.get("adapt_notes", "")),
    ]
    for row in rows:
        ws.append(row)

    # ????
    issues = result.get("audit_issues") or []
    if issues:
        ws.append([])
        ws.append(["????"])
        for i, issue in enumerate(issues, 1):
            ws.append([f"?? {i}", issue])

    # Prompt
    ws.append([])
    ws.append(["?? Prompt", result.get("prompt_text", "")])
    ws.append(["?????", result.get("negative_prompt", "")])

    # ????
    if result.get("results"):
        ws.append([])
        ws.append(["??????"])
        ws.append(["??", result.get("total", "")])
        ws.append(["??", result.get("succeeded", "")])
        ws.append(["??", result.get("failed", "")])
        ws.append([])
        ws.append(["?? ID", "??", "??"])
        for r in result["results"]:
            ws.append([r.get("shot_id", ""), r.get("status", ""), r.get("error", "")])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=pipeline_{task_id[:8]}.xlsx"},
    )
