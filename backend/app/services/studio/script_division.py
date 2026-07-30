"""剧本分镜写库服务：将分镜结果落到 Chapter/Shot/ShotDetail。"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.studio import CameraAngle, CameraMovement, CameraShotType, Chapter, Shot, ShotDetail, VFXType
from app.schemas.skills.script_processing import ScriptDivisionResult
from app.services.common import entity_not_found, require_entity


def _safe_camera_shot(val: str | None) -> CameraShotType:
    """将 LLM 输出的景别字符串安全映射为枚举值。"""
    if not val:
        return CameraShotType.ms
    mapping = {v.value.upper(): v for v in CameraShotType}
    return mapping.get(val.upper().strip(), CameraShotType.ms)


def _safe_camera_angle(val: str | None) -> CameraAngle:
    """将 LLM 输出的机位字符串安全映射为枚举值。"""
    if not val:
        return CameraAngle.eye_level
    mapping = {v.value.upper(): v for v in CameraAngle}
    return mapping.get(val.upper().strip(), CameraAngle.eye_level)


def _safe_camera_movement(val: str | None) -> CameraMovement:
    """将 LLM 输出的运镜字符串安全映射为枚举值。"""
    if not val:
        return CameraMovement.static
    mapping = {v.value.upper(): v for v in CameraMovement}
    return mapping.get(val.upper().strip(), CameraMovement.static)


def _append_division_rows(
    db_add,
    *,
    chapter_id: str,
    result: ScriptDivisionResult,
) -> None:
    for shot_division in result.shots:
        title = (shot_division.shot_name or "").strip() or f"镜头 {shot_division.index}"
        shot_id = str(uuid.uuid4())
        db_add(
            Shot(
                id=shot_id,
                chapter_id=chapter_id,
                index=shot_division.index,
                title=title,
                script_excerpt=shot_division.script_excerpt,
            )
        )
        db_add(
            ShotDetail(
                id=shot_id,
                camera_shot=_safe_camera_shot(shot_division.camera_shot),
                angle=_safe_camera_angle(shot_division.camera_angle),
                movement=_safe_camera_movement(shot_division.camera_movement),
                description=shot_division.description or "",
                duration=shot_division.duration or 4,
                mood_tags=shot_division.mood_tags or [],
                atmosphere=shot_division.atmosphere or "",
                follow_atmosphere=True,
                vfx_type=VFXType.none,
            )
        )


async def write_division_result_to_chapter(
    db: AsyncSession,
    *,
    chapter_id: str,
    result: ScriptDivisionResult,
) -> None:
    """将分镜结果写入指定章节；若章节已有镜头则拒绝写入。"""
    await require_entity(
        db,
        Chapter,
        chapter_id,
        detail=entity_not_found("Chapter"),
        status_code=400,
    )

    existing = await db.execute(select(Shot.id).where(Shot.chapter_id == chapter_id).limit(1))
    if existing.first() is not None:
        raise HTTPException(
            status_code=400,
            detail="Chapter already has shots; refusing to write (write_strategy=fail)",
        )

    _append_division_rows(db.add, chapter_id=chapter_id, result=result)

    # 触发唯一约束与外键检查，确保在返回前失败。
    await db.flush()


def write_division_result_to_chapter_sync(
    db: Session,
    *,
    chapter_id: str,
    result: ScriptDivisionResult,
) -> None:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=400, detail=entity_not_found("Chapter"))

    existing = db.execute(select(Shot.id).where(Shot.chapter_id == chapter_id).limit(1))
    if existing.first() is not None:
        raise HTTPException(
            status_code=400,
            detail="Chapter already has shots; refusing to write (write_strategy=fail)",
        )

    _append_division_rows(db.add, chapter_id=chapter_id, result=result)
    db.flush()
