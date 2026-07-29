"""novel_codex_agent Prompt 引擎 API 路由。

提供 3 个端点:
- POST /generate     异步启动 Prompt 生成
- GET  /status/{id}  查询任务进度
- GET  /result/{id}  获取生成结果
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import ApiResponse, success_response
from app.schemas.novel_codex import (
    NovelCodexGenerateRequest,
    NovelCodexResultRead,
)
from app.services.novel_codex_bridge import bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novel-codex", tags=["novel-codex"])


@router.post(
    "/generate",
    response_model=ApiResponse[dict],
    summary="一键生成高质量视频 Prompt",
    description=(
        "为指定章节调用 novel_codex_agent 6 步 Pipeline 生成视频 Prompt。"
        "Pipeline 在后台线程执行, 返回 task_id 供前端轮询。"
    ),
)
async def generate_prompts(
    body: NovelCodexGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """启动 Prompt 生成任务。"""
    try:
        task_id = await bridge.generate_for_chapter(
            db,
            chapter_id=body.chapter_id,
            director_ids=body.director_ids,
            target_models=body.target_models,
            enable_cards=body.enable_storyboard_cards,
            text_model_id=body.text_model_id,
        )
        return success_response(data={
            "task_id": task_id,
            "status": "pending",
            "message": "Prompt 生成任务已启动",
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to start novel_codex task")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start task: {e}",
        )


@router.get(
    "/status/{task_id}",
    response_model=ApiResponse[dict],
    summary="查询 Prompt 生成任务状态",
)
async def get_task_status(task_id: str) -> ApiResponse[dict]:
    """查询任务进度。"""
    try:
        result = await bridge.get_task_status(task_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/result/{task_id}",
    response_model=ApiResponse[NovelCodexResultRead],
    summary="获取 Prompt 生成结果",
)
async def get_task_result(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NovelCodexResultRead]:
    """获取结果并写回 DB。"""
    try:
        result = await bridge.get_task_result(task_id, db)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get novel_codex result")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get result: {e}",
        )
