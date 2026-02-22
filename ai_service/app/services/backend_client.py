"""Async HTTP client for the DB backend REST API.

Wraps all backend endpoints needed by the AI service:
  - Location: countries, regions, cities, addresses, offices
  - Managers: positions, skills, managers, manager-skills
  - Tickets:  segments, genders, tickets, ticket-analysis

Uses httpx with connection pooling. All methods are idempotent-safe:
they search-first then create, returning existing records when found.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("ai_service.backend_client")


class BackendClient:
    """Async client for the DB backend REST API."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # ── lifecycle ─────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                timeout=self._timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── generic helpers ──────────────────────────────────────────────

    async def _post(self, path: str, json: dict) -> dict:
        client = await self._get_client()
        resp = await client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        client = await self._get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _put(self, path: str, json: dict) -> dict:
        client = await self._get_client()
        resp = await client.put(path, json=json)
        resp.raise_for_status()
        return resp.json()

    # ── find-or-create pattern ───────────────────────────────────────

    async def _find_or_create(
        self,
        list_path: str,
        create_path: str,
        search_field: str,
        search_value: str,
        create_payload: dict,
    ) -> dict:
        """Search for record by field value; create if not found."""
        items = await self._get(list_path)
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        for item in items:
            if str(item.get(search_field, "")).strip().lower() == search_value.strip().lower():
                return item
        return await self._post(create_path, create_payload)

    # ══════════════════════════════════════════════════════════════════
    # LOCATION
    # ══════════════════════════════════════════════════════════════════

    async def find_or_create_country(self, name: str) -> dict:
        return await self._find_or_create(
            "/location/countries", "/location/countries",
            "name", name, {"name": name},
        )

    async def find_or_create_region(self, name: str, country_id: int) -> dict:
        items = await self._get("/location/regions")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        for item in items:
            if (str(item.get("name", "")).strip().lower() == name.strip().lower()
                    and item.get("country_id") == country_id):
                return item
        return await self._post("/location/regions", {
            "name": name, "country_id": country_id,
        })

    async def find_or_create_city(self, name: str, region_id: int) -> dict:
        items = await self._get("/location/cities")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        for item in items:
            if (str(item.get("name", "")).strip().lower() == name.strip().lower()
                    and item.get("region_id") == region_id):
                return item
        return await self._post("/location/cities", {
            "name": name, "region_id": region_id,
        })

    async def find_or_create_address(
        self, country_id: int, region_id: int, city_id: int,
        street: str, home_number: str,
    ) -> dict:
        items = await self._get("/location/addresses")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        for item in items:
            if (item.get("country_id") == country_id
                    and item.get("region_id") == region_id
                    and item.get("city_id") == city_id
                    and str(item.get("street", "")).strip().lower() == street.strip().lower()
                    and str(item.get("home_number", "")).strip().lower() == home_number.strip().lower()):
                return item
        return await self._post("/location/addresses", {
            "country_id": country_id,
            "region_id": region_id,
            "city_id": city_id,
            "street": street or "-",
            "home_number": home_number or "-",
        })

    async def get_address(self, address_id: int) -> dict:
        return await self._get(f"/location/addresses/{address_id}")

    async def get_city(self, city_id: int) -> dict:
        return await self._get(f"/location/cities/{city_id}")

    async def get_region(self, region_id: int) -> dict:
        return await self._get(f"/location/regions/{region_id}")

    async def get_country(self, country_id: int) -> dict:
        return await self._get(f"/location/countries/{country_id}")

    async def resolve_address_query(self, address_id: int) -> str:
        """Resolve an address_id into a geocoding query string.

        Fetches address → city → region → country names and
        builds "street building, city, region, country".
        """
        try:
            addr = await self.get_address(address_id)
            street = addr.get("street", "")
            home = addr.get("home_number", "")

            city_name = ""
            region_name = ""
            country_name = ""

            if addr.get("city_id"):
                city = await self.get_city(addr["city_id"])
                city_name = city.get("name", "")
                if city.get("region_id"):
                    region = await self.get_region(city["region_id"])
                    region_name = region.get("name", "")
                    if region.get("country_id"):
                        country = await self.get_country(region["country_id"])
                        country_name = country.get("name", "")

            street_part = " ".join(p.strip() for p in [street, home] if p.strip() and p.strip() != "-")
            parts = [street_part, city_name, region_name, country_name]
            return ", ".join(p.strip() for p in parts if p.strip())
        except Exception as e:
            logger.warning("Failed to resolve address %d: %s", address_id, e)
            return ""

    async def find_or_create_office(self, city_id: int, address: str) -> dict:
        items = await self._get("/location/offices")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        for item in items:
            if item.get("city_id") == city_id:
                return item
        return await self._post("/location/offices", {
            "city_id": city_id, "address": address,
        })

    async def get_offices(self) -> list[dict]:
        """Return all offices."""
        items = await self._get("/location/offices")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_cities(self) -> list[dict]:
        """Return all cities."""
        items = await self._get("/location/cities")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    # ══════════════════════════════════════════════════════════════════
    # MANAGERS
    # ══════════════════════════════════════════════════════════════════

    async def find_or_create_position(self, name: str, hierarchy_level: int = 0) -> dict:
        return await self._find_or_create(
            "/managers/positions", "/managers/positions",
            "name", name, {"name": name, "hierarchy_level": hierarchy_level},
        )

    async def find_or_create_skill(self, name: str) -> dict:
        return await self._find_or_create(
            "/managers/skills", "/managers/skills",
            "name", name, {"name": name},
        )

    async def create_manager(
        self, position_id: int, city_id: int,
        skill_ids: list[int], in_progress_requests: int = 0,
    ) -> dict:
        return await self._post("/managers/", {
            "position_id": position_id,
            "city_id": city_id,
            "in_progress_requests": in_progress_requests,
            "skill_ids": skill_ids,
        })

    async def get_managers(self) -> list[dict]:
        items = await self._get("/managers/")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_managers_expanded(self) -> list[dict]:
        """Fetch all managers with position, city, and skills expanded.

        Uses the bulk list endpoint with expand flags — the backend now
        handles batch relation fetching in O(1) bulk queries.
        """
        items = await self._get(
            "/managers",
            params={
                "expand_position": "true",
                "expand_city": "true",
                "expand_skills": "true",
            },
        )
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_positions(self) -> list[dict]:
        """Return all manager positions."""
        items = await self._get("/managers/positions")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_skills(self) -> list[dict]:
        """Return all skills."""
        items = await self._get("/managers/skills")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    # ══════════════════════════════════════════════════════════════════
    # TICKETS
    # ══════════════════════════════════════════════════════════════════

    async def find_or_create_gender(self, name: str) -> dict:
        return await self._find_or_create(
            "/tickets/genders", "/tickets/genders",
            "name", name, {"name": name},
        )

    async def find_or_create_segment(self, name: str, priority: int = 0) -> dict:
        return await self._find_or_create(
            "/tickets/segments", "/tickets/segments",
            "name", name, {"name": name, "priority": priority},
        )

    async def create_ticket(
        self, ticket_id: str, gender_id: int, date_of_birth: str,
        description: str, segment_id: int, address_id: int,
    ) -> dict:
        return await self._post("/tickets/", {
            "id_": ticket_id,
            "gender_id": gender_id,
            "date_of_birth": date_of_birth,
            "description": description,
            "segment_id": segment_id,
            "address_id": address_id,
        })

    async def get_tickets(self) -> list[dict]:
        items = await self._get("/tickets/")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_tickets_with_attachments(self) -> list[dict]:
        """Fetch all tickets with expanded attachments and presigned URLs."""
        items = await self._get(
            "/tickets/",
            params={
                "expand": "true",
                "include_attachments": "true",
                "include_attachment_type": "true",
                "include_attachment_url": "true",
            },
        )
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_ticket(self, ticket_id: str) -> dict:
        return await self._get(f"/tickets/{ticket_id}")

    # ══════════════════════════════════════════════════════════════════
    # TICKET ANALYSIS
    # ══════════════════════════════════════════════════════════════════

    async def create_ticket_analysis(
        self,
        ticket_id: str,
        request_type: str,
        sentiment: str,
        urgency_score: int,
        language: str,
        summary: str,
        image_enriched: bool = False,
        latitude: float | None = None,
        longitude: float | None = None,
        formatted_address: str = "",
    ) -> dict:
        payload: dict[str, Any] = {
            "ticket_id": ticket_id,
            "request_type": request_type,
            "sentiment": sentiment,
            "urgency_score": urgency_score,
            "language": language,
            "summary": summary,
            "image_enriched": image_enriched,
            "formatted_address": formatted_address,
        }
        if latitude is not None:
            payload["latitude"] = latitude
        if longitude is not None:
            payload["longitude"] = longitude
        return await self._post("/tickets/analysis", payload)

    async def get_ticket_analyses(self) -> list[dict]:
        items = await self._get("/tickets/analysis")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def get_ticket_analysis(self, ticket_id: str) -> dict | None:
        try:
            return await self._get(f"/tickets/analysis/{ticket_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ══════════════════════════════════════════════════════════════════
    # ANALYSIS META (Task Latencies, Retries Used, Analysis Meta)
    # ══════════════════════════════════════════════════════════════════

    async def create_task_latencies(self, latencies: dict) -> dict:
        return await self._post("/tickets/task-latencies", latencies)

    async def create_retries_used(self, retries: dict) -> dict:
        return await self._post("/tickets/retries-used", retries)

    async def create_analysis_meta(
        self,
        ticket_id: str,
        model: str,
        task_latencies_id: int,
        retries_used_id: int,
        fallbacks_used: list[str],
        total_processing_ms: float,
    ) -> dict:
        return await self._post("/tickets/analysis-meta", {
            "ticket_id": ticket_id,
            "model": model,
            "task_latencies_id": task_latencies_id,
            "retries_used_id": retries_used_id,
            "fallbacks_used": fallbacks_used,
            "total_processing_ms": total_processing_ms,
        })

    async def get_analysis_meta_list(self, expand: bool = True) -> list[dict]:
        items = await self._get(f"/tickets/analysis-meta?expand={str(expand).lower()}")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    # ══════════════════════════════════════════════════════════════════
    # ATTACHMENTS
    # ══════════════════════════════════════════════════════════════════

    async def list_attachment_types(self) -> list[dict]:
        items = await self._get("/tickets/attachment-types")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    async def create_attachment_type(self, name: str) -> dict:
        return await self._post("/tickets/attachment-types", {"name": name})

    async def find_or_create_attachment_type(self, name: str, *, _cache: dict | None = None) -> int:
        """Return the id of an attachment type, creating if needed."""
        if _cache is not None and name in _cache:
            return _cache[name]
        types = await self.list_attachment_types()
        for t in types:
            if (t.get("name") or "").lower() == name.lower():
                if _cache is not None:
                    _cache[name] = t["id_"]
                return t["id_"]
        created = await self.create_attachment_type(name)
        if _cache is not None:
            _cache[name] = created["id_"]
        return created["id_"]

    async def create_attachment(self, type_id: int, key: str) -> dict:
        return await self._post(
            "/tickets/attachments",
            {"type_id": type_id, "key": key},
        )

    async def link_attachments_to_ticket(self, ticket_id: str, attachment_ids: list[int]) -> dict:
        return await self._put(
            f"/tickets/{ticket_id}",
            {"attachment_ids": attachment_ids},
        )

    # ══════════════════════════════════════════════════════════════════
    # SEGMENTS
    # ══════════════════════════════════════════════════════════════════

    async def get_segments(self) -> list[dict]:
        """Return all client segments."""
        items = await self._get("/tickets/segments")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    # ══════════════════════════════════════════════════════════════════
    # TICKET ASSIGNMENTS
    # ══════════════════════════════════════════════════════════════════

    async def create_ticket_assignment(self, ticket_id: str, manager_id: int) -> dict:
        return await self._post("/tickets/assignments", {
            "ticket_id": ticket_id,
            "manager_id": manager_id,
        })

    async def get_ticket_assignments(self) -> list[dict]:
        items = await self._get("/tickets/assignments")
        if isinstance(items, dict) and "items" in items:
            items = items["items"]
        return items

    # ══════════════════════════════════════════════════════════════════
    # HEALTH
    # ══════════════════════════════════════════════════════════════════

    async def health(self) -> dict:
        return await self._get("/health")
