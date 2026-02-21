"""CSV → AnalyzeTicketRequest converter.

Parses an uploaded CSV file (UTF-8 or UTF-8-BOM) and maps columns from the
hackathon ticket dataset into validated ``AnalyzeTicketRequest`` objects.

Expected CSV columns (Russian headers — order does not matter):
  GUID клиента | Описание | Вложения | Сегмент клиента |
  Страна | Область | Населённый пункт | Улица | Дом

Unknown / extra columns are silently ignored.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field

from app.core.logging import get_logger
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
    """Map column indices to semantic field names.

    Returns ``{col_index: field_name}`` for recognised columns.
    """
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(headers):
        normalised = raw.strip().lower()
        # Remove BOM character if present
        normalised = normalised.lstrip("\ufeff")
        if normalised in _COLUMN_MAP:
            mapping[idx] = _COLUMN_MAP[normalised]
    return mapping


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
    if isinstance(content, bytes):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            # Fallback to cp1251 (common in CIS region CSV exports)
            try:
                text = content.decode("cp1251")
                logger.info("CSV decoded with cp1251 fallback")
            except UnicodeDecodeError:
                result.errors.append("Не удалось декодировать CSV. Поддерживаемые кодировки: UTF-8, CP1251.")
                return result
    else:
        text = content

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
