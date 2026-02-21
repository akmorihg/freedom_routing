"""Router: POST /ai/analyze-ticket, POST /ai/analyze-batch, POST /ai/upload-csv."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.requests import AnalyzeBatchRequest, AnalyzeTicketRequest
from app.schemas.responses import AnalyzeBatchResponse, AnalyzeTicketResponse
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.csv_handler import parse_csv
from app.services.result_store import save_result

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
        "request received ticket_id=%s text_len=%d attachments=%d",
        body.ticket_id,
        len(body.description),
        len(body.attachments),
    )

    orchestrator = AnalysisOrchestrator(settings)
    try:
        response = await orchestrator.analyze(
            ticket_id=body.ticket_id,
            description=body.description,
            segment=body.segment.value,
            attachments=body.attachments or None,
            address_query=body.address.to_query() if body.address else "",
        )
    except Exception:
        logger.exception("Unhandled error analyzing ticket %s", body.ticket_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed unexpectedly. Please retry.",
        )

    # Save result to JSON file for observation
    await save_result(response.model_dump())

    return response


@router.post(
    "/analyze-batch",
    response_model=AnalyzeBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse a batch of tickets",
    description=(
        "Accepts a list of tickets and analyses them in parallel with "
        "controlled concurrency. Returns all results at once."
    ),
)
async def analyze_batch(
    body: AnalyzeBatchRequest,
) -> AnalyzeBatchResponse:
    """Analyse multiple tickets with semaphore-controlled concurrency."""
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured.",
        )

    concurrency = min(body.concurrency, settings.batch_max_concurrency)
    logger.info(
        "batch request: %d tickets, concurrency=%d",
        len(body.tickets),
        concurrency,
    )

    orchestrator = AnalysisOrchestrator(settings)
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_one(ticket: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
        async with semaphore:
            return await orchestrator.analyze(
                ticket_id=ticket.ticket_id,
                description=ticket.description,
                segment=ticket.segment.value,
                attachments=ticket.attachments or None,
                address_query=ticket.address.to_query() if ticket.address else "",
            )

    t_start = time.perf_counter()

    tasks = [_process_one(t) for t in body.tickets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_ms = (time.perf_counter() - t_start) * 1000

    # Separate successes and errors
    successful: list[AnalyzeTicketResponse] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(
                "batch ticket %s failed: %s",
                body.tickets[i].ticket_id,
                res,
            )
        else:
            successful.append(res)
            # Save each result
            await save_result(res.model_dump())

    logger.info(
        "batch completed: %d/%d succeeded in %.1fms",
        len(successful),
        len(body.tickets),
        total_ms,
    )

    return AnalyzeBatchResponse(
        results=successful,
        total_tickets=len(body.tickets),
        total_processing_ms=round(total_ms, 1),
    )


# ── CSV endpoints ────────────────────────────────────────────────────────


@router.post(
    "/preview-csv",
    status_code=status.HTTP_200_OK,
    summary="Preview CSV parsing (no analysis)",
    description=(
        "Upload a CSV file to see how it would be parsed into tickets. "
        "Returns parsed tickets and any parsing errors without running LLM analysis."
    ),
)
async def preview_csv(
    file: UploadFile = File(..., description="CSV file with ticket data"),
) -> JSONResponse:
    """Parse CSV and return preview of extracted tickets (no LLM calls)."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    result = parse_csv(content)

    if result.errors and not result.tickets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "CSV parsing failed — no valid tickets found.",
                "errors": result.errors,
            },
        )

    return JSONResponse(
        content={
            "total_rows": result.total_rows,
            "parsed_tickets": len(result.tickets),
            "skipped_rows": result.skipped_rows,
            "errors": result.errors,
            "tickets": [t.model_dump(mode="json") for t in result.tickets],
        },
        media_type="application/json; charset=utf-8",
    )


@router.post(
    "/upload-csv",
    response_model=AnalyzeBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload CSV and analyse all tickets",
    description=(
        "Upload a CSV file with ticket data. The file is parsed, validated, "
        "and all tickets are analysed in parallel (like /analyze-batch). "
        "Supports the hackathon ticket CSV format."
    ),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with ticket data"),
    concurrency: int = Query(default=5, ge=1, le=20, description="Max parallel analyses"),
) -> AnalyzeBatchResponse:
    """Parse CSV, convert to tickets, and run batch analysis."""
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured.",
        )

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are accepted.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Parse CSV
    csv_result = parse_csv(content)

    if not csv_result.tickets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "No valid tickets found in CSV.",
                "errors": csv_result.errors,
                "skipped_rows": csv_result.skipped_rows,
            },
        )

    logger.info(
        "CSV upload: %s — %d tickets parsed (%d skipped), concurrency=%d",
        file.filename,
        len(csv_result.tickets),
        csv_result.skipped_rows,
        concurrency,
    )

    # Run batch analysis (reuse the same logic)
    concurrency = min(concurrency, settings.batch_max_concurrency)
    orchestrator = AnalysisOrchestrator(settings)
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_one(ticket: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
        async with semaphore:
            return await orchestrator.analyze(
                ticket_id=ticket.ticket_id,
                description=ticket.description,
                segment=ticket.segment.value,
                attachments=ticket.attachments or None,
                address_query=ticket.address.to_query() if ticket.address else "",
            )

    t_start = time.perf_counter()

    tasks = [_process_one(t) for t in csv_result.tickets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_ms = (time.perf_counter() - t_start) * 1000

    successful: list[AnalyzeTicketResponse] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            logger.error(
                "CSV batch ticket %s failed: %s",
                csv_result.tickets[i].ticket_id,
                res,
            )
        else:
            successful.append(res)
            await save_result(res.model_dump())

    logger.info(
        "CSV batch completed: %d/%d succeeded in %.1fms",
        len(successful),
        len(csv_result.tickets),
        total_ms,
    )

    return AnalyzeBatchResponse(
        results=successful,
        total_tickets=len(csv_result.tickets),
        total_processing_ms=round(total_ms, 1),
    )


@router.get(
    "/results",
    summary="View stored analysis results",
    description="Returns all analysis results saved to the local JSON file.",
)
async def get_results(
    last: int = Query(default=0, ge=0, description="Return only the last N results (0 = all)"),
) -> JSONResponse:
    """Return stored analysis results from the JSON file."""
    results_file = Path("results/analysis_results.json")
    if not results_file.exists():
        return JSONResponse(content=[], media_type="application/json; charset=utf-8")

    try:
        data = json.loads(results_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=500, detail="Results file is corrupted.")

    if last > 0:
        data = data[-last:]

    return JSONResponse(content=data, media_type="application/json; charset=utf-8")
