"""Router: CSV upload endpoints that parse and store data into DB via backend API.

POST /data/upload-managers       → parse managers.csv → DB
POST /data/upload-business-units → parse business_units.csv → DB
POST /data/upload-tickets        → parse tickets.csv → DB
POST /data/upload-all            → upload all 3 CSVs at once → DB
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.backend_client import BackendClient
from app.services.csv_handler import (
    parse_csv,
    parse_managers_csv,
    parse_business_units_csv,
)

logger = get_logger("router.data")
router = APIRouter(prefix="/data", tags=["Data Upload"])

# Position name → hierarchy level mapping
_POSITION_LEVELS: dict[str, int] = {
    "специалист": 1,
    "ведущий специалист": 2,
    "главный специалист": 3,
}

# Segment name → priority mapping
_SEGMENT_PRIORITY: dict[str, int] = {
    "mass": 0,
    "vip": 2,
    "priority": 1,
}

# Default country for Kazakhstan offices
_DEFAULT_COUNTRY = "Казахстан"

# City → canonical region mapping for Kazakhstan.
# Used when the CSV row has no explicit Область column (managers, BUs).
_CITY_REGION_MAP: dict[str, str] = {
    "актау": "Мангистауская область",
    "актобе": "Актюбинская область",
    "алматы": "г. Алматы",
    "астана": "г. Астана",
    "атырау": "Атырауская область",
    "караганда": "Карагандинская область",
    "кокшетау": "Акмолинская область",
    "костанай": "Костанайская область",
    "кызылорда": "Кызылординская область",
    "павлодар": "Павлодарская область",
    "петропавловск": "Северо-Казахстанская область",
    "тараз": "Жамбылская область",
    "уральск": "Западно-Казахстанская область",
    "усть-каменогорск": "Восточно-Казахстанская область",
    "шымкент": "г. Шымкент",
    # smaller towns from tickets.csv
    "тургень": "Алматинская область",
    "красный яр": "Восточно-Казахстанская область",
    "шортанды": "Акмолинская область",
    "осакаровка": "Карагандинская область",
    "косшы": "Акмолинская область",
    "ленгер": "Туркестанская область",
    "кентау": "Туркестанская область",
    "аксу": "Павлодарская область",
    "кыргауылды": "Алматинская область",
    "сарань": "Карагандинская область",
    "кокпекты": "Абайская область",
    "индербор": "Атырауская область",
    "бадам": "Туркестанская область",
    "бескарагай": "Восточно-Казахстанская область",
    "шардара": "Туркестанская область",
    "конаев": "Алматинская область",
    "капчагай": "Алматинская область",
    "кокпек": "Алматинская область",
    "туркестан": "Туркестанская область",
    "aktau": "Мангистауская область",
}


def _infer_region(city_name: str, csv_region: str = "") -> str:
    """Return the best region name: explicit CSV value → city lookup → country fallback."""
    if csv_region and csv_region.strip():
        return csv_region.strip()
    key = city_name.strip().lower()
    # handle composite like "Конаев (Капчагай)"
    if "(" in key:
        inner = key.split("(")[1].rstrip(")")
        if inner in _CITY_REGION_MAP:
            return _CITY_REGION_MAP[inner]
    if key in _CITY_REGION_MAP:
        return _CITY_REGION_MAP[key]
    # Try prefix match for names like "Косшы / Астана"
    for part in key.split("/"):
        part = part.strip()
        if part in _CITY_REGION_MAP:
            return _CITY_REGION_MAP[part]
    return _DEFAULT_COUNTRY   # fallback


# ── helpers ──────────────────────────────────────────────────────────────


def _get_backend() -> BackendClient:
    """Create a BackendClient with the configured URL."""
    return BackendClient(base_url=get_settings().backend_url)


async def _read_csv_file(file: UploadFile) -> bytes:
    """Validate and read an uploaded CSV file."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only .csv files are accepted. Got: {file.filename!r}",
        )
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file {file.filename!r} is empty.",
        )
    return content


async def _ensure_country(bc: BackendClient) -> int:
    """Ensure default country exists, return country_id."""
    country = await bc.find_or_create_country(_DEFAULT_COUNTRY)
    return country["id_"]


async def _resolve_region_id(
    bc: BackendClient,
    country_id: int,
    region_name: str,
    region_cache: dict[str, int],
) -> int:
    """Get or create a region by name, with caching."""
    key = region_name.strip().lower()
    if key not in region_cache:
        region = await bc.find_or_create_region(region_name.strip(), country_id)
        region_cache[key] = region["id_"]
    return region_cache[key]


_DOB_ISO = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DOB_DOT = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _parse_dob(raw: str | None) -> str:
    """Parse date of birth from CSV into YYYY-MM-DD string."""
    if not raw:
        return "2000-01-01"
    raw = raw.strip()
    m = _DOB_ISO.match(raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = _DOB_DOT.match(raw)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return "2000-01-01"


# ── managers ─────────────────────────────────────────────────────────────

@router.post(
    "/upload-managers",
    status_code=status.HTTP_200_OK,
    summary="Upload managers.csv → DB",
    description="Parse managers CSV and store positions, skills, managers into DB.",
)
async def upload_managers(
    file: UploadFile = File(..., description="managers.csv"),
) -> JSONResponse:
    content = await _read_csv_file(file)
    result = parse_managers_csv(content)

    if result.errors and not result.managers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "No valid managers found.", "errors": result.errors},
        )

    bc = _get_backend()
    try:
        country_id = await _ensure_country(bc)

        # Caches: name → DB id
        position_cache: dict[str, int] = {}
        skill_cache: dict[str, int] = {}
        city_cache: dict[str, int] = {}
        region_cache: dict[str, int] = {}

        created_managers = 0
        db_errors: list[str] = []

        for mgr in result.managers:
            try:
                # Position
                pos_name = (mgr.position or "специалист").strip().lower()
                if pos_name not in position_cache:
                    level = _POSITION_LEVELS.get(pos_name, 1)
                    pos = await bc.find_or_create_position(pos_name, level)
                    position_cache[pos_name] = pos["id_"]
                position_id = position_cache[pos_name]

                # Skills
                skill_ids: list[int] = []
                for sk in mgr.skills:
                    sk_lower = sk.strip().lower()
                    if sk_lower and sk_lower not in skill_cache:
                        skill = await bc.find_or_create_skill(sk_lower)
                        skill_cache[sk_lower] = skill["id_"]
                    if sk_lower:
                        skill_ids.append(skill_cache[sk_lower])

                # Region (inferred from city for managers CSV)  
                city_name = (mgr.office or "Алматы").strip()
                region_name = _infer_region(city_name)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)

                # City
                if city_name not in city_cache:
                    city = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = city["id_"]
                city_id = city_cache[city_name]

                # Create manager
                await bc.create_manager(
                    position_id=position_id,
                    city_id=city_id,
                    skill_ids=skill_ids,
                    in_progress_requests=mgr.current_load,
                )
                created_managers += 1

            except Exception as e:
                db_errors.append(f"Manager '{mgr.name}': {e}")
                logger.warning("Failed to store manager %s: %s", mgr.name, e)

        logger.info("Managers stored: %d/%d", created_managers, len(result.managers))

        return JSONResponse(
            content={
                "file": file.filename,
                "total_rows": result.total_rows,
                "parsed": len(result.managers),
                "stored": created_managers,
                "skipped_rows": result.skipped_rows,
                "parse_errors": result.errors,
                "db_errors": db_errors,
            },
            media_type="application/json; charset=utf-8",
        )
    finally:
        await bc.close()


# ── business units ───────────────────────────────────────────────────────

@router.post(
    "/upload-business-units",
    status_code=status.HTTP_200_OK,
    summary="Upload business_units.csv → DB",
    description="Parse business units CSV and store offices into DB.",
)
async def upload_business_units(
    file: UploadFile = File(..., description="business_units.csv"),
) -> JSONResponse:
    content = await _read_csv_file(file)
    result = parse_business_units_csv(content)

    if result.errors and not result.units:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "No valid business units found.", "errors": result.errors},
        )

    bc = _get_backend()
    try:
        country_id = await _ensure_country(bc)

        city_cache: dict[str, int] = {}
        region_cache: dict[str, int] = {}
        created_offices = 0
        db_errors: list[str] = []

        for unit in result.units:
            try:
                city_name = (unit.office or "Алматы").strip()
                region_name = _infer_region(city_name)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)

                if city_name not in city_cache:
                    city = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = city["id_"]
                city_id = city_cache[city_name]

                addr_str = unit.address or "-"
                await bc.find_or_create_office(city_id=city_id, address=addr_str)
                created_offices += 1

            except Exception as e:
                db_errors.append(f"Office '{unit.office}': {e}")
                logger.warning("Failed to store office %s: %s", unit.office, e)

        logger.info("Offices stored: %d/%d", created_offices, len(result.units))

        return JSONResponse(
            content={
                "file": file.filename,
                "total_rows": result.total_rows,
                "parsed": len(result.units),
                "stored": created_offices,
                "skipped_rows": result.skipped_rows,
                "parse_errors": result.errors,
                "db_errors": db_errors,
            },
            media_type="application/json; charset=utf-8",
        )
    finally:
        await bc.close()


# ── tickets ──────────────────────────────────────────────────────────────

@router.post(
    "/upload-tickets",
    status_code=status.HTTP_200_OK,
    summary="Upload tickets.csv → DB",
    description="Parse tickets CSV and store into DB (no LLM analysis).",
)
async def upload_tickets(
    file: UploadFile = File(..., description="tickets.csv"),
) -> JSONResponse:
    content = await _read_csv_file(file)
    result = parse_csv(content)

    if result.errors and not result.tickets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "No valid tickets found.", "errors": result.errors},
        )

    bc = _get_backend()
    try:
        country_id = await _ensure_country(bc)

        gender_cache: dict[str, int] = {}
        segment_cache: dict[str, int] = {}
        city_cache: dict[str, int] = {}
        region_cache: dict[str, int] = {}

        created_tickets = 0
        db_errors: list[str] = []
        att_type_cache: dict[str, int] = {}

        for ticket in result.tickets:
            try:
                # Gender
                gender_name = (ticket.gender or "unknown").strip().lower()
                if gender_name not in gender_cache:
                    g = await bc.find_or_create_gender(gender_name)
                    gender_cache[gender_name] = g["id_"]
                gender_id = gender_cache[gender_name]

                # Segment
                seg_name = (ticket.segment.value if ticket.segment else "mass").strip().lower()
                if seg_name not in segment_cache:
                    priority = _SEGMENT_PRIORITY.get(seg_name, 0)
                    s = await bc.find_or_create_segment(seg_name, priority)
                    segment_cache[seg_name] = s["id_"]
                segment_id = segment_cache[seg_name]

                # Region (from CSV Область column, or inferred from city)
                addr = ticket.address
                city_name = (addr.city if addr and addr.city else "Алматы").strip()
                csv_region = addr.region if addr else ""
                region_name = _infer_region(city_name, csv_region)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)

                # City
                if city_name not in city_cache:
                    c = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = c["id_"]
                city_id = city_cache[city_name]

                # Address
                address = await bc.find_or_create_address(
                    country_id=country_id,
                    region_id=region_id,
                    city_id=city_id,
                    street=addr.street if addr else "",
                    home_number=addr.building if addr else "",
                )
                address_id = address["id_"]

                # Date of birth
                dob = _parse_dob(ticket.date_of_birth)

                # Create ticket
                ticket_resp = await bc.create_ticket(
                    ticket_id=ticket.ticket_id,
                    gender_id=gender_id,
                    date_of_birth=dob,
                    description=ticket.description,
                    segment_id=segment_id,
                    address_id=address_id,
                )
                created_ticket_id = ticket_resp.get("id_") or ticket.ticket_id
                created_tickets += 1

                # Handle attachments from CSV (Вложения column)
                if ticket.attachments:
                    att_ids: list[int] = []
                    for fname in ticket.attachments:
                        try:
                            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                            mime_map = {
                                "png": "image/png", "jpg": "image/jpeg",
                                "jpeg": "image/jpeg", "gif": "image/gif",
                                "webp": "image/webp", "pdf": "application/pdf",
                            }
                            mime = mime_map.get(ext, "application/octet-stream")
                            type_id = await bc.find_or_create_attachment_type(
                                mime, _cache=att_type_cache,
                            )
                            s3_key = f"tickets/{created_ticket_id}/{fname}"
                            att = await bc.create_attachment(type_id, s3_key)
                            att_ids.append(att["id_"])
                        except Exception as att_err:
                            db_errors.append(
                                f"Attachment '{fname}' for ticket {created_ticket_id}: {att_err}"
                            )
                    if att_ids:
                        try:
                            await bc.link_attachments_to_ticket(created_ticket_id, att_ids)
                        except Exception as link_err:
                            db_errors.append(
                                f"Linking attachments to ticket {created_ticket_id}: {link_err}"
                            )

            except Exception as e:
                db_errors.append(f"Ticket '{ticket.ticket_id}': {e}")
                logger.warning("Failed to store ticket %s: %s", ticket.ticket_id, e)

        logger.info("Tickets stored: %d/%d", created_tickets, len(result.tickets))

        return JSONResponse(
            content={
                "file": file.filename,
                "total_rows": result.total_rows,
                "parsed": len(result.tickets),
                "stored": created_tickets,
                "skipped_rows": result.skipped_rows,
                "parse_errors": result.errors,
                "db_errors": db_errors,
            },
            media_type="application/json; charset=utf-8",
        )
    finally:
        await bc.close()


# ── upload all 3 at once ────────────────────────────────────────────────

@router.post(
    "/upload-all",
    status_code=status.HTTP_200_OK,
    summary="Upload all 3 CSV files at once → DB",
    description=(
        "Accepts tickets.csv, managers.csv, and business_units.csv in a single "
        "multipart request. Stores everything into DB. "
        "Upload order: business_units → managers → tickets."
    ),
)
async def upload_all(
    tickets: UploadFile = File(..., description="tickets.csv"),
    managers: UploadFile = File(..., description="managers.csv"),
    business_units: UploadFile = File(..., description="business_units.csv"),
) -> JSONResponse:
    """Parse all three CSV files and store into DB.

    Upload order: business units first (creates offices/cities),
    then managers (reuses cities), then tickets.
    """
    tickets_content = await _read_csv_file(tickets)
    managers_content = await _read_csv_file(managers)
    bu_content = await _read_csv_file(business_units)

    tickets_result = parse_csv(tickets_content)
    managers_result = parse_managers_csv(managers_content)
    bu_result = parse_business_units_csv(bu_content)

    logger.info(
        "Bulk upload parsed: tickets=%d managers=%d units=%d",
        len(tickets_result.tickets),
        len(managers_result.managers),
        len(bu_result.units),
    )

    bc = _get_backend()
    try:
        country_id = await _ensure_country(bc)

        # Shared caches
        city_cache: dict[str, int] = {}
        region_cache: dict[str, int] = {}
        position_cache: dict[str, int] = {}
        skill_cache: dict[str, int] = {}
        gender_cache: dict[str, int] = {}
        segment_cache: dict[str, int] = {}

        # ── 1. Business units (offices) ──
        bu_stored = 0
        bu_errors: list[str] = []
        for unit in bu_result.units:
            try:
                city_name = (unit.office or "Алматы").strip()
                region_name = _infer_region(city_name)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)
                if city_name not in city_cache:
                    c = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = c["id_"]
                await bc.find_or_create_office(city_id=city_cache[city_name], address=unit.address or "-")
                bu_stored += 1
            except Exception as e:
                bu_errors.append(f"Office '{unit.office}': {e}")

        # ── 2. Managers ──
        mgr_stored = 0
        mgr_errors: list[str] = []
        for mgr in managers_result.managers:
            try:
                pos_name = (mgr.position or "специалист").strip().lower()
                if pos_name not in position_cache:
                    level = _POSITION_LEVELS.get(pos_name, 1)
                    pos = await bc.find_or_create_position(pos_name, level)
                    position_cache[pos_name] = pos["id_"]

                skill_ids: list[int] = []
                for sk in mgr.skills:
                    sk_lower = sk.strip().lower()
                    if sk_lower and sk_lower not in skill_cache:
                        skill = await bc.find_or_create_skill(sk_lower)
                        skill_cache[sk_lower] = skill["id_"]
                    if sk_lower:
                        skill_ids.append(skill_cache[sk_lower])

                city_name = (mgr.office or "Алматы").strip()
                region_name = _infer_region(city_name)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)
                if city_name not in city_cache:
                    c = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = c["id_"]

                await bc.create_manager(
                    position_id=position_cache[pos_name],
                    city_id=city_cache[city_name],
                    skill_ids=skill_ids,
                    in_progress_requests=mgr.current_load,
                )
                mgr_stored += 1
            except Exception as e:
                mgr_errors.append(f"Manager '{mgr.name}': {e}")

        # ── 3. Tickets ──
        tkt_stored = 0
        tkt_errors: list[str] = []
        for ticket in tickets_result.tickets:
            try:
                gender_name = (ticket.gender or "unknown").strip().lower()
                if gender_name not in gender_cache:
                    g = await bc.find_or_create_gender(gender_name)
                    gender_cache[gender_name] = g["id_"]

                seg_name = (ticket.segment.value if ticket.segment else "mass").strip().lower()
                if seg_name not in segment_cache:
                    priority = _SEGMENT_PRIORITY.get(seg_name, 0)
                    s = await bc.find_or_create_segment(seg_name, priority)
                    segment_cache[seg_name] = s["id_"]

                addr = ticket.address
                city_name = (addr.city if addr and addr.city else "Алматы").strip()
                csv_region = addr.region if addr else ""
                region_name = _infer_region(city_name, csv_region)
                region_id = await _resolve_region_id(bc, country_id, region_name, region_cache)
                if city_name not in city_cache:
                    c = await bc.find_or_create_city(city_name, region_id)
                    city_cache[city_name] = c["id_"]

                address = await bc.find_or_create_address(
                    country_id=country_id,
                    region_id=region_id,
                    city_id=city_cache[city_name],
                    street=addr.street if addr else "",
                    home_number=addr.building if addr else "",
                )

                dob = _parse_dob(ticket.date_of_birth)

                await bc.create_ticket(
                    ticket_id=ticket.ticket_id,
                    gender_id=gender_cache[gender_name],
                    date_of_birth=dob,
                    description=ticket.description,
                    segment_id=segment_cache[seg_name],
                    address_id=address["id_"],
                )
                tkt_stored += 1
            except Exception as e:
                tkt_errors.append(f"Ticket '{ticket.ticket_id}': {e}")

        logger.info(
            "Bulk store: offices=%d managers=%d tickets=%d",
            bu_stored, mgr_stored, tkt_stored,
        )

        return JSONResponse(
            content={
                "business_units": {
                    "file": business_units.filename,
                    "total_rows": bu_result.total_rows,
                    "parsed": len(bu_result.units),
                    "stored": bu_stored,
                    "errors": bu_errors,
                },
                "managers": {
                    "file": managers.filename,
                    "total_rows": managers_result.total_rows,
                    "parsed": len(managers_result.managers),
                    "stored": mgr_stored,
                    "errors": mgr_errors,
                },
                "tickets": {
                    "file": tickets.filename,
                    "total_rows": tickets_result.total_rows,
                    "parsed": len(tickets_result.tickets),
                    "stored": tkt_stored,
                    "errors": tkt_errors,
                },
            },
            media_type="application/json; charset=utf-8",
        )
    finally:
        await bc.close()
