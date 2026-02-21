"""Internal domain models for managers, business units, and analysis results.

These are *transport / internal* representations — NOT SQLAlchemy / DB models.
The DB team will create ORM models that mirror these fields.
Conversion helpers ``to_dict()`` are provided for easy hand-off.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# Manager
# ═══════════════════════════════════════════════════════════════════════════

class Manager(BaseModel):
    """Internal representation of a manager from managers.csv.

    Fields
    ------
    name:          Display name (e.g. "Менеджер 1")
    position:      Job title — one of:
                   Специалист | Ведущий специалист | Главный специалист
    office:        City name of the office (FK to BusinessUnit.office)
    skills:        List of skill tags: "VIP", "ENG", "KZ"
    current_load:  Number of tickets currently in progress (0+)
    """

    name: str = Field(..., min_length=1)
    position: str = Field(..., min_length=1)
    office: str = Field(..., min_length=1, description="City name — FK to business_units")
    skills: list[str] = Field(default_factory=list, description="e.g. ['VIP', 'ENG', 'KZ']")
    current_load: int = Field(default=0, ge=0, description="Tickets currently assigned")


# ═══════════════════════════════════════════════════════════════════════════
# Business Unit (Office / Branch)
# ═══════════════════════════════════════════════════════════════════════════

class BusinessUnit(BaseModel):
    """Internal representation of a branch office from business_units.csv.

    Fields
    ------
    office:   City name (unique key, e.g. "Алматы")
    address:  Full physical address string
    latitude / longitude:  Geocoded coordinates (filled after geocoding)
    """

    office: str = Field(..., min_length=1, description="City name — unique key")
    address: str = Field(default="", description="Full physical address")
    latitude: float | None = Field(default=None, description="Geocoded latitude")
    longitude: float | None = Field(default=None, description="Geocoded longitude")


# ═══════════════════════════════════════════════════════════════════════════
# Ticket Analysis Result  (what goes into the DB — no metadata)
# ═══════════════════════════════════════════════════════════════════════════

class TicketAnalysisResult(BaseModel):
    """Flat representation of a fully-analysed ticket for DB storage.

    This is the schema the DB team should model their table after.
    No processing metadata (latencies, retries, model name) — just
    the business-relevant fields.

    Suggested DB table name: ``ticket_analysis``
    """

    # ── Ticket identity ──────────────────────────────────────────────────
    ticket_id: str = Field(..., description="PK — GUID from tickets.csv")

    # ── Client info (from CSV) ───────────────────────────────────────────
    client_gender: str = Field(default="", description="Пол клиента")
    client_birth_date: str = Field(default="", description="Дата рождения (ISO string)")
    segment: str = Field(default="Mass", description="Mass | VIP | Priority")

    # ── Original ticket data ─────────────────────────────────────────────
    description: str = Field(default="", description="Original ticket text")
    attachments: list[str] = Field(default_factory=list, description="Attachment filenames/URLs")

    # ── AI analysis output ───────────────────────────────────────────────
    request_type: str = Field(..., description="Classified request type (Russian label)")
    sentiment: str = Field(..., description="Позитивный | Нейтральный | Негативный")
    urgency_score: int = Field(..., ge=1, le=10)
    language: str = Field(..., description="RU | KZ | ENG")
    summary: str = Field(..., description="AI-generated summary + recommendation")
    image_enriched: bool = Field(default=False, description="True if attachments contributed to analysis")

    # ── Geo (from address + geocoding) ───────────────────────────────────
    country: str = Field(default="")
    region: str = Field(default="")
    city: str = Field(default="")
    street: str = Field(default="")
    building: str = Field(default="")
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    formatted_address: str = Field(default="")
    geo_status: str = Field(default="skipped", description="skipped | ok | fallback | error")



# ═══════════════════════════════════════════════════════════════════════════
# Ticket Assignment  (separate table — FK to ticket_analysis.ticket_id)
# ═══════════════════════════════════════════════════════════════════════════

class TicketAssignment(BaseModel):
    """Routing decision for a single ticket — filled by RoutingService.

    Suggested DB table name: ``ticket_assignment`` with FK to ``ticket_analysis``.
    """

    # ── Identity ─────────────────────────────────────────────────────────
    ticket_id: str = Field(..., description="FK → ticket_analysis.ticket_id")

    # ── Assignment result ────────────────────────────────────────────────
    assigned_manager: str | None = Field(
        default=None, description="Manager name who received the ticket",
    )

    round_robin_index: int | None = Field(
        default=None,
        description="0-based index in the round-robin pair for this office",
    )

