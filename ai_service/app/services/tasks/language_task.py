"""Task: detect language via LLM with validation and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.core.validation import normalize_language
from app.schemas.enums import Language
from app.services.llm_client import LLMClient

logger = get_logger("task.language")

FALLBACK = Language.RU


async def run(
    llm: LLMClient,
    description: str,
    *,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
    image_urls: list[str] | None = None,
) -> tuple[Language, int, bool]:
    """Detect language of the ticket text.

    Returns
    -------
    tuple[Language, retries_used, fallback_used]
    """
    try:
        lang, retries = await retry_with_timeout(
            lambda: _attempt(llm, description, image_urls),
            task_name="language",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return lang, retries, False
    except Exception:
        logger.warning("language: all attempts failed → fallback %s", FALLBACK.value)
        return FALLBACK, max_retries, True


async def _attempt(llm: LLMClient, description: str, image_urls: list[str] | None = None) -> Language:
    raw = await llm.detect_language(description, image_urls=image_urls)
    logger.debug("language raw=%r", raw)
    return normalize_language(raw)
