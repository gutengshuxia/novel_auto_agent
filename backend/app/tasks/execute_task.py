"""统一 Celery 执行入口（celery 可选）。

没有 celery 时，enqueue/revoke 直接 no-op，后台异步任务通过同步方式降级。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# celery 为可选依赖
celery_available = False
try:
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app
    celery_available = True
except ImportError:
    logger.warning("celery not installed: async task dispatching disabled")

from app.core.db_sync import sync_session_maker
from app.models.task import GenerationTask
from app.services.worker.task_registry import task_executor_registry


def _record_executor_dispatch(task_id: str, *, executor_type: str, executor_task_id: str | None) -> None:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        row.executor_type = executor_type
        row.executor_task_id = executor_task_id
        db.commit()


def enqueue_task_execution(task_id: str):
    if not celery_available:
        logger.warning("celery not available, skipping task %s", task_id)
        return None
    async_result = run_task_celery.delay(task_id)
    _record_executor_dispatch(task_id, executor_type="celery", executor_task_id=async_result.id)
    return async_result


def revoke_task_execution(task_id: str, *, terminate: bool = True, signal: str = "SIGTERM") -> bool:
    if not celery_available:
        return False
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return False
        if (row.executor_type or "").strip() != "celery":
            return False
        executor_task_id = (row.executor_task_id or "").strip()
        if not executor_task_id:
            return False
    try:
        AsyncResult(executor_task_id, app=celery_app).revoke(terminate=terminate, signal=signal)
    except Exception:
        logger.exception("failed to revoke celery task: task_id=%s executor_task_id=%s", task_id, executor_task_id)
        return False
    return True


if celery_available:
    @celery_app.task(name="task.execute")
    def run_task_celery(task_id: str) -> None:
        with sync_session_maker() as db:
            row = db.get(GenerationTask, task_id)
            if row is None:
                return
            task_kind = (row.task_kind or "").strip() or str((row.payload or {}).get("task_kind") or "").strip()
        executor = task_executor_registry.resolve(task_kind)
        executor.run(task_id)
else:
    def run_task_celery(task_id: str) -> None:
        raise RuntimeError("celery not available")
