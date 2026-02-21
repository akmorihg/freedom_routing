"""Async Google Maps Geocoding client."""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger("geo_client")

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeoClient:
    """Thin async wrapper around the Google Maps Geocoding API.

    Returns (latitude, longitude, formatted_address) for a given query string.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def geocode(self, address_query: str) -> tuple[float, float, str]:
        """Geocode an address string.

        Returns
        -------
        tuple[float, float, str]
            (latitude, longitude, formatted_address)

        Raises
        ------
        ValueError
            If the API returns no results.
        RuntimeError
            If the API call itself fails.
        """
        if not address_query.strip():
            raise ValueError("Empty address query")

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _GEOCODE_URL,
                params={
                    "address": address_query,
                    "key": self._api_key,
                    "language": "ru",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "UNKNOWN")
        if status != "OK":
            raise ValueError(f"Geocoding failed: status={status} for query={address_query!r}")

        result = data["results"][0]
        loc = result["geometry"]["location"]
        formatted = result.get("formatted_address", "")

        logger.debug(
            "geocoded %r → (%.6f, %.6f) %s",
            address_query, loc["lat"], loc["lng"], formatted,
        )

        return loc["lat"], loc["lng"], formatted
