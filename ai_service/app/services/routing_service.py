"""Manager routing / assignment service.

Implements §3.2 business rules with a **heuristic approach**:

1. **Competency filter** – hard-skill / position gate
   • VIP or Priority segment  →  manager must have ``vip`` skill
   • KZ language              →  manager must have ``kz`` skill
   • ENG language             →  manager must have ``eng`` skill
   • Data-change request type →  manager needs ``главный специалист`` (L3)

2. **Geo + Load heuristic** – single score per eligible manager
   ``score = haversine_km(ticket, office) + LOAD_PENALTY * manager.load``
   Lower score wins. This naturally distributes work to farther but
   less-loaded managers when local ones are busy.

3. **Unknown / foreign address** – ticket has no lat/lon
   Alternate 50 / 50 between Астана and Алматы offices (the two
   largest hubs), then pick by load within the preferred city.

4. **Urgency ordering** – tickets are processed highest-urgency first
   so the most critical ones get the best-scoring managers.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass

from app.services.backend_client import BackendClient
from app.services.geo_client import GeoClient
from app.schemas.domain import TicketAssignment

logger = logging.getLogger("ai_service.routing")

# ── tunables ─────────────────────────────────────────────────────────────

# 1 extra in-progress ticket = this many km of "virtual distance".
# 150 means: a manager 150 km farther with 1 fewer ticket is equally
# attractive — this aggressively redistributes away from hot-spots.
LOAD_PENALTY_KM: float = 150.0

# Penalty for a manager in a non-preferred city when ticket has no location
NO_GEO_NON_PREFERRED_KM: float = 500.0

# Large penalty for a manager whose office failed geocoding
UNGEOCODABLE_OFFICE_KM: float = 2000.0

# Known city-name variants for fallback routing
_ASTANA_NAMES = frozenset({"астана", "нур-султан", "nur-sultan", "astana"})
_ALMATY_NAMES = frozenset({"алматы", "almaty"})

# Keywords that indicate a "data-change" request type → level-3 requirement
_DATA_CHANGE_KW = ("изменение данных", "изменение", "data change", "смена данных")


# ── lightweight data carriers ────────────────────────────────────────────

@dataclass(slots=True)
class OfficeGeo:
    city_id: int
    city_name: str
    latitude: float
    longitude: float


@dataclass(slots=True)
class ManagerInfo:
    id: int
    city_id: int
    position_name: str
    hierarchy_level: int
    skills: list[str]
    base_load: int            # load from DB at start of routing run


# ── service ──────────────────────────────────────────────────────────────

class RoutingService:
    """Assign analysed tickets to managers using a geo + load heuristic."""

    def __init__(
        self,
        backend_client: BackendClient,
        geo_client: GeoClient,
        *,
        load_penalty_km: float = LOAD_PENALTY_KM,
    ) -> None:
        self.bc = backend_client
        self.geo = geo_client
        self.load_penalty = load_penalty_km

        # Populated by _load_*
        self._offices: dict[int, OfficeGeo] = {}   # city_id → OfficeGeo
        self._segments: dict[int, str] = {}         # segment_id → name (lower)

    # ── data loading ─────────────────────────────────────────────────

    async def _load_office_geo(self) -> None:
        """Geocode every office and cache by *city_id*."""
        offices = await self.bc.get_offices()
        city_cache: dict[int, str] = {}

        for office in offices:
            city_id = office["city_id"]
            if city_id in self._offices:
                continue

            if city_id not in city_cache:
                city = await self.bc.get_city(city_id)
                city_cache[city_id] = city.get("name", "")

            city_name = city_cache[city_id]
            address = office.get("address", "").strip()

            query = (
                f"{address}, {city_name}, Казахстан"
                if address and address != "-"
                else f"{city_name}, Казахстан"
            )

            try:
                lat, lon, _fmt = await self.geo.geocode(query)
            except Exception:
                # fall back to just the city name
                try:
                    lat, lon, _fmt = await self.geo.geocode(f"{city_name}, Казахстан")
                except Exception as exc:
                    logger.warning("Cannot geocode office city=%s: %s", city_name, exc)
                    continue

            self._offices[city_id] = OfficeGeo(
                city_id=city_id,
                city_name=city_name,
                latitude=lat,
                longitude=lon,
            )
            logger.debug("Geocoded office %s → (%.4f, %.4f)", city_name, lat, lon)

        logger.info("Loaded %d geocoded offices", len(self._offices))

    async def _load_segments(self) -> None:
        segments = await self.bc.get_segments()
        self._segments = {
            s["id_"]: s.get("name", "").strip().lower()
            for s in segments
        }
        logger.info("Loaded %d segments", len(self._segments))

    async def _load_managers(self) -> list[ManagerInfo]:
        raw = await self.bc.get_managers_expanded()
        result: list[ManagerInfo] = []
        for m in raw:
            pos = m.get("position") or {}
            skills = [s.get("name", "").strip().lower() for s in (m.get("skills") or [])]
            result.append(ManagerInfo(
                id=m["id_"],
                city_id=m.get("city_id", 0),
                position_name=pos.get("name", "").strip().lower(),
                hierarchy_level=pos.get("hierarchy_level", 0),
                skills=skills,
                base_load=m.get("in_progress_requests", 0),
            ))
        logger.info("Loaded %d managers", len(result))
        return result

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in kilometres."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.asin(min(1.0, math.sqrt(a)))

    def _find_hub_cities(self) -> tuple[int | None, int | None]:
        """Return (astana_city_id, almaty_city_id) from loaded offices."""
        astana = almaty = None
        for cid, geo in self._offices.items():
            low = geo.city_name.strip().lower()
            if low in _ASTANA_NAMES:
                astana = cid
            elif low in _ALMATY_NAMES:
                almaty = cid
        return astana, almaty

    @staticmethod
    def _is_eligible(
        mgr: ManagerInfo,
        segment_name: str,
        language: str,
        request_type: str,
    ) -> bool:
        """Hard-skill / position gate."""
        # VIP / Priority segment → need VIP skill
        if segment_name in ("vip", "priority") and "vip" not in mgr.skills:
            return False
        # KZ language → need kz skill
        if language == "KZ" and "kz" not in mgr.skills:
            return False
        # ENG language → need eng skill
        if language == "ENG" and "eng" not in mgr.skills:
            return False
        # Data-change request → главный специалист (hierarchy_level ≥ 3)
        req_low = request_type.lower()
        if any(kw in req_low for kw in _DATA_CHANGE_KW):
            if mgr.hierarchy_level < 3:
                return False
        return True

    # ── main entry point ─────────────────────────────────────────────

    async def assign_all(self) -> list[TicketAssignment]:
        """Run full routing: load data → filter → score → assign → store.

        Returns the list of assignments created (also persisted to DB).
        """
        # 1. Load reference data
        await self._load_office_geo()
        await self._load_segments()
        managers = await self._load_managers()
        analyses = await self.bc.get_ticket_analyses()
        tickets = await self.bc.get_tickets()

        # Existing assignments → skip
        existing = await self.bc.get_ticket_assignments()
        already_assigned: set[str] = {str(a.get("ticket_id", "")) for a in existing}

        # Ticket lookup for segment resolution
        ticket_map: dict[str, dict] = {
            str(t.get("id_", t.get("id", ""))): t
            for t in tickets
        }

        # Running load tracker (starts at DB value, increments on assign)
        load: dict[int, int] = {m.id: m.base_load for m in managers}

        astana_cid, almaty_cid = self._find_hub_cities()
        fallback_counter = 0

        # Process highest-urgency tickets first
        analyses.sort(key=lambda a: a.get("urgency_score", 1), reverse=True)

        assignments: list[TicketAssignment] = []

        for analysis in analyses:
            ticket_id = str(analysis.get("ticket_id", ""))
            if ticket_id in already_assigned:
                continue

            ticket = ticket_map.get(ticket_id, {})
            lat = analysis.get("latitude")
            lon = analysis.get("longitude")
            language = (analysis.get("language") or "RU").upper()
            request_type = analysis.get("request_type", "")
            segment_name = self._segments.get(ticket.get("segment_id"), "mass")

            has_location = (
                lat is not None
                and lon is not None
                and not (lat == 0.0 and lon == 0.0)
            )

            # ── competency filter ────────────────────────────────────
            eligible = [
                m for m in managers
                if self._is_eligible(m, segment_name, language, request_type)
            ]
            if not eligible:
                # Relax position constraint first
                eligible = [
                    m for m in managers
                    if self._is_eligible(m, segment_name, language, "")
                ]
            if not eligible:
                # Last resort — any manager
                eligible = list(managers)
                logger.warning(
                    "No skill-matched managers for ticket %s – using all",
                    ticket_id,
                )

            # ── score each eligible manager ──────────────────────────
            scored: list[tuple[ManagerInfo, float]] = []

            for m in eligible:
                m_load = load.get(m.id, m.base_load)

                if has_location:
                    if m.city_id in self._offices:
                        ofc = self._offices[m.city_id]
                        dist = self._haversine_km(lat, lon, ofc.latitude, ofc.longitude)
                    else:
                        dist = UNGEOCODABLE_OFFICE_KM
                else:
                    # Unknown address → prefer Astana / Almaty alternating
                    preferred = astana_cid if fallback_counter % 2 == 0 else almaty_cid
                    dist = 0.0 if (preferred and m.city_id == preferred) else NO_GEO_NON_PREFERRED_KM

                score = dist + self.load_penalty * m_load
                scored.append((m, score))

            if not has_location:
                fallback_counter += 1

            scored.sort(key=lambda x: x[1])
            best_mgr, best_score = scored[0]

            # Update running load
            load[best_mgr.id] = load.get(best_mgr.id, 0) + 1

            assignments.append(TicketAssignment(
                ticket_id=ticket_id,
                assigned_manager=best_mgr.id,
                round_robin_index=load[best_mgr.id],
                heuristic_score=round(best_score, 2),
            ))

            logger.info(
                "Ticket %s → Manager %d  score=%.1f  (seg=%s lang=%s)",
                ticket_id, best_mgr.id, best_score, segment_name, language,
            )

        # ── persist to DB ────────────────────────────────────────────
        stored = 0
        store_errors: list[str] = []
        for a in assignments:
            try:
                await self.bc.create_ticket_assignment(
                    ticket_id=a.ticket_id,
                    manager_id=a.assigned_manager,   # type: ignore[arg-type]
                )
                stored += 1
            except Exception as exc:
                store_errors.append(f"{a.ticket_id}: {exc}")
                logger.warning("Failed to store assignment %s: %s", a.ticket_id, exc)

        logger.info(
            "Routing complete: %d assigned, %d stored, %d store-errors",
            len(assignments), stored, len(store_errors),
        )
        return assignments
