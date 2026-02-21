"""Task: geocode client address via Google Maps API with retry and fallback."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.retry import retry_with_timeout
from app.services.geo_client import GeoClient

logger = get_logger("task.geo")

# Fallback: no coordinates
FALLBACK: tuple[float | None, float | None, str, str] = (None, None, "", "fallback")


async def run(
    geo_client: GeoClient,
    address_query: str,
    *,
    max_retries: int = 2,
    timeout: float = 5.0,
    base_delay: float = 0.3,
) -> tuple[tuple[float | None, float | None, str, str], int, bool]:
    """Geocode an address.

    Returns
    -------
    tuple[(lat, lon, formatted_address, status), retries_used, fallback_used]
    """
    if not address_query.strip():
        logger.info("geo: empty address → skipped")
        return (None, None, "", "skipped"), 0, False

    try:
        (lat, lon, formatted), retries = await retry_with_timeout(
            lambda: _attempt(geo_client, address_query),
            task_name="geo",
            max_retries=max_retries,
            timeout_seconds=timeout,
            base_delay=base_delay,
        )
        return (lat, lon, formatted, "ok"), retries, False
    except Exception:
        logger.warning("geo: all attempts failed → fallback")
        return FALLBACK, max_retries, True


async def _attempt(
    geo_client: GeoClient, address_query: str,
) -> tuple[float, float, str]:
    return await geo_client.geocode(address_query)
