"""Simple JSON file-based result store for observing analysis output.

Writes each analysis result as a JSON object appended to a list in
``results/analysis_results.json``.  Thread-safe via ``asyncio.Lock``.

This is a temporary solution until the DB is connected.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger("result_store")

_RESULTS_DIR = Path("results")
_RESULTS_FILE = _RESULTS_DIR / "analysis_results.json"
_lock = asyncio.Lock()


async def save_result(data: dict[str, Any]) -> None:
    """Append a single analysis result to the JSON file.

    Creates the directory and file on first call.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }

    async with _lock:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        existing: list[dict[str, Any]] = []
        if _RESULTS_FILE.exists():
            try:
                existing = json.loads(_RESULTS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Corrupted results file — starting fresh")
                existing = []

        existing.append(record)
        _RESULTS_FILE.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    logger.info("result saved for ticket_id=%s (%d total)", data.get("ticket_id"), len(existing))
