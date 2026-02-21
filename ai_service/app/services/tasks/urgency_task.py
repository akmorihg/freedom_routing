"""Task: estimate urgency score via LLM with validation and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.core.validation import normalize_urgency
from app.services.llm_client import LLMClient

logger = get_logger("task.urgency")

FALLBACK_SCORE = 5


async def run(
    llm: LLMClient,
    description: str,
    *,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
) -> tuple[int, int, bool]:
    """Estimate urgency.

    Returns
    -------
    tuple[urgency_score, retries_used, fallback_used]
    """
    try:
        score, retries = await retry_with_timeout(
            lambda: _attempt(llm, description),
            task_name="urgency_score",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return score, retries, False
    except Exception:
        logger.warning("urgency_score: all attempts failed → fallback %d", FALLBACK_SCORE)
        return FALLBACK_SCORE, max_retries, True


async def _attempt(llm: LLMClient, description: str) -> int:
    raw = await llm.estimate_urgency(description)
    logger.debug("urgency raw=%r", raw)
    return normalize_urgency(raw)
