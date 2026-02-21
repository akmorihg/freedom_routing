"""Task: classify request type via LLM with validation and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.core.validation import normalize_request_type
from app.schemas.enums import RequestType
from app.services.llm_client import LLMClient

logger = get_logger("task.request_type")

FALLBACK = RequestType.CONSULTATION  # Консультация


async def run(
    llm: LLMClient,
    description: str,
    *,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
    image_urls: list[str] | None = None,
) -> tuple[RequestType, int, bool]:
    """Classify request type.

    Returns
    -------
    tuple[RequestType, retries_used, fallback_used]
    """
    try:
        raw, retries = await retry_with_timeout(
            lambda: _attempt(llm, description, image_urls),
            task_name="request_type",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return raw, retries, False
    except Exception:
        logger.warning("request_type: all attempts failed → fallback %s", FALLBACK.value)
        return FALLBACK, max_retries, True


async def _attempt(llm: LLMClient, description: str, image_urls: list[str] | None = None) -> RequestType:
    raw = await llm.classify_request_type(description, image_urls=image_urls)
    logger.debug("request_type raw=%r", raw)
    return normalize_request_type(raw)
