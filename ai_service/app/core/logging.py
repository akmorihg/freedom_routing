"""Structured logging setup for the AI analysis service."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a clean, structured format.

    Safe to call multiple times — only the first call takes effect.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger with the given *name*."""
    return logging.getLogger(f"ai_service.{name}")
