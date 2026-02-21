"""Task: classify sentiment via LLM with validation and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.core.validation import normalize_sentiment
from app.schemas.enums import Sentiment
from app.services.llm_client import LLMClient

logger = get_logger("task.sentiment")

FALLBACK = Sentiment.NEUTRAL  # Нейтральный


async def run(
    llm: LLMClient,
    description: str,
    *,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
) -> tuple[Sentiment, int, bool]:
    """Classify sentiment.

    Returns
    -------
    tuple[Sentiment, retries_used, fallback_used]
    """
    try:
        raw, retries = await retry_with_timeout(
            lambda: _attempt(llm, description),
            task_name="sentiment",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return raw, retries, False
    except Exception:
        logger.warning("sentiment: all attempts failed → fallback %s", FALLBACK.value)
        return FALLBACK, max_retries, True


async def _attempt(llm: LLMClient, description: str) -> Sentiment:
    raw = await llm.classify_sentiment(description)
    logger.debug("sentiment raw=%r", raw)
    return normalize_sentiment(raw)
