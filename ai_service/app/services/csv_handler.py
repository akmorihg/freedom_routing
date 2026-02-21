"""CSV parsers for all hackathon data files.

Handles three CSV formats:
  1. **tickets.csv**        → list[AnalyzeTicketRequest]
  2. **managers.csv**       → list[Manager]
  3. **business_units.csv** → list[BusinessUnit]

All parsers:
  - Accept raw bytes or str
  - Handle UTF-8 BOM and CP1251 fallback
  - Normalise column names (Russian + English aliases)
  - Return a typed result with parsed items, skip count, and per-row errors
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from typing import TypeVar

from app.core.logging import get_logger
from app.schemas.domain import BusinessUnit, Manager
from app.schemas.enums import Segment
from app.schemas.requests import AddressInfo, AnalyzeTicketRequest

logger = get_logger("csv_handler")

# ── Column name mapping ──────────────────────────────────────────────────
# Keys are *normalised* (stripped + lowered) CSV header names.
# Values are semantic field identifiers used internally.
_COLUMN_MAP: dict[str, str] = {
    "guid клиента": "ticket_id",
    "guid": "ticket_id",
    "ticket_id": "ticket_id",
    "id": "ticket_id",
    # --
    "описание": "description",
    "описание ": "description",  # trailing space in real CSV
    "description": "description",
    # --
    "вложения": "attachments",
    "attachments": "attachments",
    # --
    "сегмент клиента": "segment",
    "сегмент": "segment",
    "segment": "segment",
    # --
    "страна": "country",
    "country": "country",
    # --
    "область": "region",
    "region": "region",
    # --
    "населённый пункт": "city",
    "населенный пункт": "city",  # without ё
    "город": "city",
    "city": "city",
    # --
    "улица": "street",
    "street": "street",
    # --
    "дом": "building",
    "building": "building",
    "house": "building",
}

_SEGMENT_MAP: dict[str, Segment] = {
    "mass": Segment.MASS,
    "масс": Segment.MASS,
    "vip": Segment.VIP,
    "вип": Segment.VIP,
    "priority": Segment.PRIORITY,
    "приоритет": Segment.PRIORITY,
}


@dataclass
class CSVParseResult:
    """Outcome of CSV parsing."""

    tickets: list[AnalyzeTicketRequest] = field(default_factory=list)
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)
    total_rows: int = 0


def _resolve_columns(headers: list[str]) -> dict[int, str]:
    """Map column indices to semantic field names for tickets CSV."""
    return _resolve_columns_generic(headers, _COLUMN_MAP)


def _parse_segment(raw: str) -> Segment:
    """Convert raw segment string to Segment enum with fallback."""
    key = raw.strip().lower()
    return _SEGMENT_MAP.get(key, Segment.MASS)


def _parse_attachments(raw: str) -> list[str]:
    """Split attachment field into list of URLs / filenames.

    Supports comma-separated and semicolon-separated values.
    """
    if not raw or not raw.strip():
        return []
    # Try semicolon first (common in Excel exports), then comma
    if ";" in raw:
        parts = raw.split(";")
    else:
        parts = raw.split(",")
    return [p.strip() for p in parts if p.strip()]


def parse_csv(content: bytes | str, *, encoding: str = "utf-8-sig") -> CSVParseResult:
    """Parse CSV content into a list of ``AnalyzeTicketRequest``.

    Parameters
    ----------
    content:
        Raw CSV bytes (from file upload) or string.
    encoding:
        Character encoding to decode bytes. Default handles UTF-8 BOM.

    Returns
    -------
    CSVParseResult with parsed tickets, skip count, and any per-row errors.
    """
    result = CSVParseResult()

    # Decode bytes → str
    text = _decode_csv_bytes(content, encoding)
    if text is None:
        result.errors.append("Не удалось декодировать CSV. Поддерживаемые кодировки: UTF-8, CP1251.")
        return result

    reader = csv.reader(io.StringIO(text))

    # Read header row
    try:
        headers = next(reader)
    except StopIteration:
        result.errors.append("CSV файл пуст или не содержит заголовка.")
        return result

    col_map = _resolve_columns(headers)

    if "ticket_id" not in col_map.values() and "description" not in col_map.values():
        recognised = list(col_map.values())
        result.errors.append(
            f"Не найдены ожидаемые столбцы. Распознано: {recognised}. "
            f"Ожидается минимум 'GUID клиента' или 'Описание'."
        )
        return result

    has_ticket_id = "ticket_id" in col_map.values()
    has_description = "description" in col_map.values()

    logger.info(
        "CSV columns resolved: %s (of %d total)",
        {v: headers[k] for k, v in col_map.items()},
        len(headers),
    )

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        result.total_rows += 1

        if not any(cell.strip() for cell in row):
            result.skipped_rows += 1
            continue

        # Build field dict from column mapping
        fields: dict[str, str] = {}
        for idx, field_name in col_map.items():
            if idx < len(row):
                fields[field_name] = row[idx].strip()

        # ticket_id: use from CSV or auto-generate
        ticket_id = fields.get("ticket_id", "").strip()
        if not ticket_id:
            if has_ticket_id:
                # Column exists but value is empty
                result.skipped_rows += 1
                result.errors.append(f"Строка {row_num}: пустой GUID клиента — пропущена.")
                continue
            else:
                # No ID column at all — generate one
                ticket_id = f"CSV-{uuid.uuid4().hex[:8].upper()}"

        # description: can be empty if attachments present
        description = fields.get("description", "")

        # attachments
        attachments = _parse_attachments(fields.get("attachments", ""))

        # Skip if no description AND no attachments
        if not description.strip() and not attachments:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: нет описания и нет вложений — пропущена.")
            continue

        # segment
        segment = _parse_segment(fields.get("segment", ""))

        # address (only build if at least one geo field is present)
        address: AddressInfo | None = None
        geo_fields = {
            "country": fields.get("country", ""),
            "region": fields.get("region", ""),
            "city": fields.get("city", ""),
            "street": fields.get("street", ""),
            "building": fields.get("building", ""),
        }
        if any(v.strip() for v in geo_fields.values()):
            address = AddressInfo(**geo_fields)

        try:
            ticket = AnalyzeTicketRequest(
                ticket_id=ticket_id,
                description=description,
                segment=segment,
                attachments=attachments,
                address=address,
            )
            result.tickets.append(ticket)
        except Exception as exc:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: ошибка валидации — {exc}")

    logger.info(
        "CSV parsed: %d tickets, %d skipped, %d errors",
        len(result.tickets),
        result.skipped_rows,
        len(result.errors),
    )
    return result


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  MANAGERS CSV                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════╝

_MANAGER_COLUMN_MAP: dict[str, str] = {
    "фио": "name",
    "имя": "name",
    "name": "name",
    # --
    "должность": "position",
    "должность ": "position",  # trailing space in real CSV
    "position": "position",
    # --
    "офис": "office",
    "office": "office",
    # --
    "навыки": "skills",
    "skills": "skills",
    # --
    "количество обращений в работе": "current_load",
    "обращения в работе": "current_load",
    "current_load": "current_load",
    "workload": "current_load",
}


@dataclass
class ManagersParseResult:
    """Outcome of managers CSV parsing."""

    managers: list[Manager] = field(default_factory=list)
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)
    total_rows: int = 0


def _parse_skills(raw: str) -> list[str]:
    """Parse comma-separated skills string into a list of tags."""
    if not raw or not raw.strip():
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def parse_managers_csv(content: bytes | str, *, encoding: str = "utf-8-sig") -> ManagersParseResult:
    """Parse managers.csv into a list of ``Manager`` objects."""
    result = ManagersParseResult()
    text = _decode_csv_bytes(content, encoding)
    if text is None:
        result.errors.append("Не удалось декодировать CSV.")
        return result

    reader = csv.reader(io.StringIO(text))

    try:
        headers = next(reader)
    except StopIteration:
        result.errors.append("CSV файл пуст.")
        return result

    col_map = _resolve_columns_generic(headers, _MANAGER_COLUMN_MAP)

    if "name" not in col_map.values():
        result.errors.append(
            f"Не найден столбец ФИО. Распознано: {list(col_map.values())}"
        )
        return result

    logger.info("Managers CSV columns: %s", {v: headers[k] for k, v in col_map.items()})

    for row_num, row in enumerate(reader, start=2):
        result.total_rows += 1

        if not any(cell.strip() for cell in row):
            result.skipped_rows += 1
            continue

        fields: dict[str, str] = {}
        for idx, fname in col_map.items():
            if idx < len(row):
                fields[fname] = row[idx].strip()

        name = fields.get("name", "").strip()
        if not name:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: пустое ФИО — пропущена.")
            continue

        try:
            manager = Manager(
                name=name,
                position=fields.get("position", "Специалист"),
                office=fields.get("office", ""),
                skills=_parse_skills(fields.get("skills", "")),
                current_load=int(fields.get("current_load", "0") or "0"),
            )
            result.managers.append(manager)
        except Exception as exc:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: ошибка валидации — {exc}")

    logger.info(
        "Managers CSV parsed: %d managers, %d skipped, %d errors",
        len(result.managers), result.skipped_rows, len(result.errors),
    )
    return result


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  BUSINESS UNITS CSV                                                  ║
# ╚═══════════════════════════════════════════════════════════════════════╝

_BU_COLUMN_MAP: dict[str, str] = {
    "офис": "office",
    "office": "office",
    "город": "office",
    "city": "office",
    # --
    "адрес": "address",
    "address": "address",
}


@dataclass
class BusinessUnitsParseResult:
    """Outcome of business_units CSV parsing."""

    units: list[BusinessUnit] = field(default_factory=list)
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)
    total_rows: int = 0


def parse_business_units_csv(
    content: bytes | str, *, encoding: str = "utf-8-sig",
) -> BusinessUnitsParseResult:
    """Parse business_units.csv into a list of ``BusinessUnit`` objects."""
    result = BusinessUnitsParseResult()
    text = _decode_csv_bytes(content, encoding)
    if text is None:
        result.errors.append("Не удалось декодировать CSV.")
        return result

    reader = csv.reader(io.StringIO(text))

    try:
        headers = next(reader)
    except StopIteration:
        result.errors.append("CSV файл пуст.")
        return result

    col_map = _resolve_columns_generic(headers, _BU_COLUMN_MAP)

    if "office" not in col_map.values():
        result.errors.append(
            f"Не найден столбец Офис. Распознано: {list(col_map.values())}"
        )
        return result

    logger.info("BU CSV columns: %s", {v: headers[k] for k, v in col_map.items()})

    for row_num, row in enumerate(reader, start=2):
        result.total_rows += 1

        if not any(cell.strip() for cell in row):
            result.skipped_rows += 1
            continue

        fields: dict[str, str] = {}
        for idx, fname in col_map.items():
            if idx < len(row):
                fields[fname] = row[idx].strip()

        office = fields.get("office", "").strip()
        if not office:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: пустой Офис — пропущена.")
            continue

        # Clean up vertical tab / non-breaking space in addresses
        address = fields.get("address", "").replace("\x0b", ", ").replace("\xa0", " ").strip()

        try:
            unit = BusinessUnit(office=office, address=address)
            result.units.append(unit)
        except Exception as exc:
            result.skipped_rows += 1
            result.errors.append(f"Строка {row_num}: ошибка валидации — {exc}")

    logger.info(
        "BU CSV parsed: %d units, %d skipped, %d errors",
        len(result.units), result.skipped_rows, len(result.errors),
    )
    return result


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║  SHARED HELPERS                                                      ║
# ╚═══════════════════════════════════════════════════════════════════════╝

def _decode_csv_bytes(content: bytes | str, encoding: str = "utf-8-sig") -> str | None:
    """Decode raw bytes to str with UTF-8 → CP1251 fallback. Returns None on failure."""
    if isinstance(content, str):
        return content
    try:
        return content.decode(encoding)
    except UnicodeDecodeError:
        try:
            logger.info("CSV decoded with cp1251 fallback")
            return content.decode("cp1251")
        except UnicodeDecodeError:
            return None


def _resolve_columns_generic(
    headers: list[str], column_map: dict[str, str],
) -> dict[int, str]:
    """Map column indices to semantic field names using a given mapping."""
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(headers):
        normalised = raw.strip().lower().lstrip("\ufeff")
        if normalised in column_map:
            mapping[idx] = column_map[normalised]
    return mapping
