"""Task: describe attachment images via multimodal LLM with retry and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.services.llm_client import LLMClient

logger = get_logger("task.image_describe")

FALLBACK_TEXT = ""


async def run(
    llm: LLMClient,
    image_urls: list[str],
    *,
    max_retries: int = 2,
    timeout: float = 8.0,
    base_delay: float = 0.3,
) -> tuple[str, int, bool]:
    """Describe attachment images.

    Returns
    -------
    tuple[description_text, retries_used, fallback_used]
    """
    if not image_urls:
        return "", 0, False

    try:
        text, retries = await retry_with_timeout(
            lambda: _attempt(llm, image_urls),
            task_name="image_describe",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return text, retries, False
    except Exception:
        logger.warning("image_describe: all attempts failed → fallback (empty)")
        return FALLBACK_TEXT, max_retries, True


async def _attempt(llm: LLMClient, image_urls: list[str]) -> str:
    raw = await llm.describe_image(image_urls)
    if not raw.strip():
        raise ValueError("Empty image description")
    logger.debug("image_describe raw=%r", raw[:120])
    return raw.strip()
