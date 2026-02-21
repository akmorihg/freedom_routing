"""Pydantic v2 request models for the analysis API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Segment


class AnalyzeTicketRequest(BaseModel):
    """POST /ai/analyze-ticket request body."""

    ticket_id: str = Field(
        ...,
        min_length=1,
        description="Unique ticket identifier (UUID or string).",
        examples=["TKT-00123"],
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Free-text client message to analyse.",
        examples=["Не могу войти в приложение уже второй день, очень расстроен."],
    )
    segment: Segment = Field(
        default=Segment.MASS,
        description="Client segment (Mass / VIP / Priority). Used for future prompt tuning.",
    )
