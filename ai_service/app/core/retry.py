"""Reusable async retry wrapper with exponential back-off and timeout."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

from app.core.logging import get_logger

logger = get_logger("retry")

T = TypeVar("T")


async def retry_with_timeout(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    task_name: str,
    max_retries: int = 2,
    timeout_seconds: float = 5.0,
    base_delay: float = 0.3,
) -> tuple[T, int]:
    """Execute *coro_factory()* with retries and a per-attempt timeout.

    Parameters
    ----------
    coro_factory:
        A **zero-arg callable** that returns a fresh awaitable each attempt.
    task_name:
        Human-readable label used in logs.
    max_retries:
        Maximum number of *additional* attempts after the first try.
    timeout_seconds:
        Per-attempt wall-clock limit (seconds).
    base_delay:
        Starting delay for exponential back-off between retries.

    Returns
    -------
    tuple[T, int]
        (result, retries_used)

    Raises
    ------
    Exception
        The last encountered exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            result = await asyncio.wait_for(
                coro_factory(),
                timeout=timeout_seconds,
            )
            if attempt > 0:
                logger.info(
                    "%s succeeded on retry %d", task_name, attempt
                )
            return result, attempt
        except asyncio.TimeoutError:
            last_exc = asyncio.TimeoutError(  # type: ignore[assignment]
                f"{task_name} timed out (attempt {attempt + 1})"
            )
            logger.warning(
                "%s timeout on attempt %d/%d",
                task_name,
                attempt + 1,
                1 + max_retries,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "%s error on attempt %d/%d: %s",
                task_name,
                attempt + 1,
                1 + max_retries,
                exc,
            )

        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]
