"""Task: generate summary + recommendation via LLM with fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.core.validation import normalize_summary
from app.services.llm_client import LLMClient

logger = get_logger("task.summary")

FALLBACK_TEXT = (
    "Не удалось автоматически сформировать выжимку. "
    "Требуется ручная проверка обращения."
)


async def run(
    llm: LLMClient,
    description: str,
    *,
    context: dict[str, str] | None = None,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
    image_urls: list[str] | None = None,
) -> tuple[str, int, bool]:
    """Summarise the ticket text.

    Parameters
    ----------
    context:
        Optional dict with resolved type/language for richer summary.

    Returns
    -------
    tuple[summary_text, retries_used, fallback_used]
    """
    try:
        text, retries = await retry_with_timeout(
            lambda: _attempt(llm, description, context, image_urls),
            task_name="summary",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return text, retries, False
    except Exception:
        logger.warning("summary: all attempts failed → fallback")
        return FALLBACK_TEXT, max_retries, True


async def _attempt(
    llm: LLMClient,
    description: str,
    context: dict[str, str] | None,
    image_urls: list[str] | None = None,
) -> str:
    raw = await llm.summarize_ticket(description, context=context, image_urls=image_urls)
    logger.debug("summary raw=%r", raw[:120])
    return normalize_summary(raw)
