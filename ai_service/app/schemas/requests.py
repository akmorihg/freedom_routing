"""Pydantic v2 request models for the analysis API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Segment


class AddressInfo(BaseModel):
    """Client address fields from the ticket CSV."""

    country: str = Field(default="", description="Country")
    region: str = Field(default="", description="Oblast / region")
    city: str = Field(default="", description="City or settlement")
    street: str = Field(default="", description="Street name")
    building: str = Field(default="", description="Building / house number")

    def to_query(self) -> str:
        """Build a single-line geocoding query from non-empty parts."""
        parts = [self.country, self.region, self.city, self.street, self.building]
        return ", ".join(p.strip() for p in parts if p.strip())


class AnalyzeTicketRequest(BaseModel):
    """POST /ai/analyze-ticket request body."""

    ticket_id: str = Field(
        ...,
        min_length=1,
        description="Unique ticket identifier (UUID or string).",
        examples=["TKT-00123"],
    )
    description: str = Field(
        default="",
        description="Free-text client message to analyse. Can be empty if attachment is provided.",
        examples=["Не могу войти в приложение уже второй день, очень расстроен."],
    )
    segment: Segment = Field(
        default=Segment.MASS,
        description="Client segment (Mass / VIP / Priority). Used for future prompt tuning.",
    )
    attachments: list[str] = Field(
        default_factory=list,
        description=(
            "List of attachment URLs (images / screenshots). "
            "Used for multimodal analysis when description is insufficient."
        ),
    )
    address: AddressInfo | None = Field(
        default=None,
        description="Client address for geo-normalization. If absent, geo is skipped.",
    )


class AnalyzeBatchRequest(BaseModel):
    """POST /ai/analyze-batch request body."""

    tickets: list[AnalyzeTicketRequest] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="List of tickets to analyse.",
    )
    concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max number of tickets processed in parallel.",
    )
