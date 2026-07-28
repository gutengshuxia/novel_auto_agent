"""统一日志配置 —— 使用 Rich 美化输出。"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from rich.logging import RichHandler


@lru_cache(maxsize=1)
def get_logger(name: str = "novel_codex_agent") -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
    )
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


__all__ = ["get_logger"]
