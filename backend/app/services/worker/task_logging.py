"""统一任务事件日志：同时输出到 Python logging 和 DB（task_log_entries 表）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_task_event(task_kind: str, task_id: str, event: str, **fields: Any) -> None:
    """输出到 Python logging（保留原有行为）。"""
    extras = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    suffix = f" {extras}" if extras else ""
    logger.info("task_event kind=%s task_id=%s event=%s%s", task_kind, task_id, event, suffix)


def log_task_failure(task_kind: str, task_id: str, error: str) -> None:
    logger.exception("task_event kind=%s task_id=%s event=failed error=%s", task_kind, task_id, error)


def write_task_log(
    db: Session,
    *,
    task_id: str,
    level: str,
    message: str,
    step: str = "",
) -> None:
    """将一条日志写入 task_log_entries 表（同步，供 worker 线程调用）。"""
    from app.models.task_log import TaskLogEntry

    db.add(
        TaskLogEntry(
            task_id=task_id,
            timestamp=datetime.now(timezone.utc),
            level=level,
            step=step,
            message=message,
        )
    )
    db.flush()
