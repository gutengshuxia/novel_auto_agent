"""任务执行日志条目模型。

用于在前端展示任务执行过程中的详细日志，让用户了解任务执行的每个阶段。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TaskLogEntry(Base):
    """任务执行日志条目表。

    每条记录对应任务执行过程中的一条日志。前端通过轮询 API 获取并展示。
    """

    __tablename__ = "task_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="日志行 ID")
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属任务 ID",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="日志时间戳",
    )
    level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="info",
        comment="日志级别：info / warn / error / success",
    )
    step: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="当前执行步骤名称（与 current_step 对应）",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="日志内容",
    )

    __table_args__ = (
        Index("ix_task_log_entries_task_id_timestamp", "task_id", "timestamp"),
    )


__all__ = ["TaskLogEntry"]
