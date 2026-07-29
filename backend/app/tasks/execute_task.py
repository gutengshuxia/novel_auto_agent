"""统一任务执行入口（支持 Celery 或线程降级）。

执行模式选择（通过环境变量 TASK_EXECUTOR_MODE 控制）:
- "thread"（默认）: 在后台线程中直接执行，无需 Celery worker
- "celery": 发送到 Celery 队列，需要单独启动 Celery worker

开发环境推荐使用 "thread" 模式，生产环境可使用 "celery" 模式。
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 执行模式: "thread"（默认）或 "celery"
EXECUTOR_MODE = os.getenv("TASK_EXECUTOR_MODE", "thread").strip().lower()

# celery 为可选依赖
celery_available = False
try:
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app
    celery_available = True
except ImportError:
    logger.info("celery not installed: only thread mode available")

from app.core.db_sync import sync_session_maker
from app.models.task import GenerationTask
from app.services.worker.task_registry import task_executor_registry

# 线程池（用于 thread 模式）
_task_thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="task-executor")


def _record_executor_dispatch(task_id: str, *, executor_type: str, executor_task_id: str | None) -> None:
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return
        row.executor_type = executor_type
        row.executor_task_id = executor_task_id
        db.commit()


def _run_task_in_thread(task_id: str) -> None:
    """在线程中直接执行任务（降级模式）。"""
    logger.info("[thread-mode] Starting task execution: %s", task_id)
    try:
        with sync_session_maker() as db:
            row = db.get(GenerationTask, task_id)
            if row is None:
                logger.warning("[thread-mode] Task not found: %s", task_id)
                return
            task_kind = (row.task_kind or "").strip() or str((row.payload or {}).get("task_kind") or "").strip()
        executor = task_executor_registry.resolve(task_kind)
        executor.run(task_id)
        logger.info("[thread-mode] Task completed: %s", task_id)
    except Exception:
        logger.exception("[thread-mode] Task failed: %s", task_id)


def enqueue_task_execution(task_id: str):
    """提交任务执行。

    根据 EXECUTOR_MODE 选择执行方式:
    - "thread": 在后台线程池中执行（默认，无需 Celery worker）
    - "celery": 发送到 Celery 队列
    """
    if EXECUTOR_MODE == "celery" and celery_available:
        # Celery 模式
        logger.info("[celery-mode] Dispatching task to Celery: %s", task_id)
        async_result = run_task_celery.delay(task_id)
        _record_executor_dispatch(task_id, executor_type="celery", executor_task_id=async_result.id)
        return async_result
    else:
        # 线程模式（默认）
        logger.info("[thread-mode] Submitting task to thread pool: %s", task_id)
        _record_executor_dispatch(task_id, executor_type="thread", executor_task_id=None)
        future = _task_thread_pool.submit(_run_task_in_thread, task_id)
        return future


def revoke_task_execution(task_id: str, *, terminate: bool = True, signal: str = "SIGTERM") -> bool:
    """取消任务执行。

    注意: thread 模式下暂不支持强制终止，只能标记 cancel_requested。
    """
    # 先标记取消（两种模式都支持）
    with sync_session_maker() as db:
        row = db.get(GenerationTask, task_id)
        if row is None:
            return False
        row.cancel_requested = True
        db.commit()

    if EXECUTOR_MODE == "celery" and celery_available:
        if (row.executor_type or "").strip() != "celery":
            return True  # thread 模式已标记取消
        executor_task_id = (row.executor_task_id or "").strip()
        if not executor_task_id:
            return True
        try:
            AsyncResult(executor_task_id, app=celery_app).revoke(terminate=terminate, signal=signal)
        except Exception:
            logger.exception("failed to revoke celery task: task_id=%s", task_id)
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


logger.info("Task executor mode: %s (celery_available=%s)", EXECUTOR_MODE, celery_available)
