"""Router: POST /ai/analyze-ticket."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.requests import AnalyzeTicketRequest
from app.schemas.responses import AnalyzeTicketResponse
from app.services.analysis_orchestrator import AnalysisOrchestrator

logger = get_logger("router.analysis")
router = APIRouter(prefix="/ai", tags=["AI Analysis"])


@router.post(
    "/analyze-ticket",
    response_model=AnalyzeTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse a client ticket using LLM",
    description=(
        "Accepts a ticket description and returns structured analysis: "
        "request type, sentiment, urgency, language, and summary with "
        "per-task latency and retry metadata."
    ),
)
async def analyze_ticket(
    body: AnalyzeTicketRequest,
) -> AnalyzeTicketResponse:
    """Orchestrate LLM analysis for a single ticket."""
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured.",
        )

    logger.info(
        "request received ticket_id=%s text_len=%d",
        body.ticket_id,
        len(body.description),
    )

    orchestrator = AnalysisOrchestrator(settings)
    try:
        response = await orchestrator.analyze(
            ticket_id=body.ticket_id,
            description=body.description,
            segment=body.segment.value,
        )
    except Exception:
        logger.exception("Unhandled error analyzing ticket %s", body.ticket_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed unexpectedly. Please retry.",
        )

    return response
