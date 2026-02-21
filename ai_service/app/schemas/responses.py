"""Pydantic v2 response models for the analysis API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import Language, RequestType, Sentiment


class AnalysisResult(BaseModel):
    """Core analysis payload."""

    request_type: RequestType
    sentiment: Sentiment
    urgency_score: int = Field(..., ge=1, le=10)
    language: Language
    summary: str = Field(..., min_length=1)


class TaskLatencies(BaseModel):
    """Per-task latency in milliseconds."""

    request_type: float = 0.0
    sentiment: float = 0.0
    urgency_score: float = 0.0
    language: float = 0.0
    summary: float = 0.0


class RetriesUsed(BaseModel):
    """Per-task retry counts."""

    request_type: int = 0
    sentiment: int = 0
    urgency_score: int = 0
    language: int = 0
    summary: int = 0


class AnalysisMeta(BaseModel):
    """Observability metadata attached to every response."""

    model: str
    task_latencies_ms: TaskLatencies = Field(default_factory=TaskLatencies)
    retries_used: RetriesUsed = Field(default_factory=RetriesUsed)
    fallbacks_used: list[str] = Field(default_factory=list)
    total_processing_ms: float = 0.0


class AnalyzeTicketResponse(BaseModel):
    """POST /ai/analyze-ticket response body."""

    ticket_id: str
    analysis: AnalysisResult
    meta: AnalysisMeta
