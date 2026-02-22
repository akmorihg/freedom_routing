"""Router: POST /ai/analyze-ticket, POST /ai/analyze-batch, POST /ai/upload-csv, POST /ai/analyze-from-db."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.requests import AnalyzeBatchRequest, AnalyzeTicketRequest
from app.schemas.responses import AnalyzeBatchResponse, AnalyzeTicketResponse
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.backend_client import BackendClient
from app.services.csv_handler import parse_csv
from app.services.result_store import save_result

logger = get_logger("router.analysis")
router = APIRouter(prefix="/ai", tags=["AI Analysis"])

# ── Helper: convert presigned MinIO URLs → base64 data URIs ──────────


def _rewrite_minio_url(url: str) -> str:
    """Replace localhost/127.0.0.1 with Docker-internal hostname 'minio'."""
    parsed = urlparse(url)
    if parsed.hostname in ("localhost", "127.0.0.1"):
        return urlunparse(parsed._replace(netloc=f"minio:{parsed.port or 9000}"))
    return url


async def _download_image_as_data_uri(url: str, timeout: float = 15.0) -> str | None:
    """Download image from MinIO and return a base64 data URI.

    Returns None on any failure so the caller can skip gracefully.
    """
    internal_url = _rewrite_minio_url(url)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(internal_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                # guess from URL path
                path = urlparse(url).path
                guessed, _ = mimetypes.guess_type(path)
                content_type = guessed or "image/png"
            b64 = base64.b64encode(resp.content).decode()
            return f"data:{content_type};base64,{b64}"
    except Exception as exc:
        logger.warning("Failed to download image %s → %s: %s", url, internal_url, exc)
        return None


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


# ── DB-backed analyze ────────────────────────────────────────────────────


@router.post(
    "/analyze-from-db",
    status_code=status.HTTP_200_OK,
    summary="Pull tickets from DB, run AI analysis, store results",
    description=(
        "Fetches all tickets from the database (via backend API), runs LLM "
        "analysis on each one, and stores the resulting TicketAnalysis back "
        "into the database. Skips tickets that already have an analysis. "
        "Returns a summary of the run."
    ),
)
async def analyze_from_db(
    concurrency: int = Query(default=5, ge=1, le=20, description="Max parallel analyses"),
    limit: int = Query(default=0, ge=0, description="Max tickets to process (0 = all)"),
) -> JSONResponse:
    """Pull tickets from DB → run LLM → store analysis results to DB."""
    settings = get_settings()

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured.",
        )

    bc = BackendClient(base_url=settings.backend_url)
    try:
        # 1. Fetch all tickets from DB (with attachment URLs for image analysis)
        all_tickets = await bc.get_tickets_with_attachments()
        logger.info("Fetched %d tickets from DB", len(all_tickets))

        # 2. Fetch existing analyses to skip already-analyzed tickets
        existing_analyses = await bc.get_ticket_analyses()
        analyzed_ids: set[str] = {
            a.get("ticket_id", "") for a in existing_analyses
        }
        logger.info("Found %d existing analyses, will skip those", len(analyzed_ids))

        # 3. Filter to un-analyzed tickets
        pending = [t for t in all_tickets if t.get("id_", t.get("id", "")) not in analyzed_ids]
        if limit > 0:
            pending = pending[:limit]

        if not pending:
            return JSONResponse(
                content={
                    "message": "No new tickets to analyze.",
                    "total_in_db": len(all_tickets),
                    "already_analyzed": len(analyzed_ids),
                    "processed": 0,
                },
                media_type="application/json; charset=utf-8",
            )

        logger.info("Will analyze %d tickets (skipped %d already analyzed)", len(pending), len(analyzed_ids))

        # 4. Run LLM analysis
        concurrency = min(concurrency, settings.batch_max_concurrency)
        orchestrator = AnalysisOrchestrator(settings)
        semaphore = asyncio.Semaphore(concurrency)

        async def _analyze_one(ticket_data: dict) -> tuple[str, AnalyzeTicketResponse | None, str | None]:
            """Returns (ticket_id, response_or_None, error_or_None)."""
            tid = ticket_data.get("id_", ticket_data.get("id", "unknown"))
            description = ticket_data.get("description", "")

            # Resolve address for geocoding
            address_query = ""
            addr_id = ticket_data.get("address_id")
            if addr_id:
                address_query = await bc.resolve_address_query(addr_id)

            # Collect presigned image URLs from attachments and convert to base64
            raw_image_urls = []
            for att in (ticket_data.get("attachments") or []):
                att_url = att.get("url")
                att_type = (att.get("type", {}) or {}).get("name", "") if isinstance(att.get("type"), dict) else ""
                att_key = att.get("key", "")
                is_image = "image" in att_type.lower() or any(
                    att_key.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")
                )
                if att_url and is_image:
                    raw_image_urls.append(att_url)

            # Download images from MinIO and convert to base64 data URIs
            # (presigned URLs use localhost:9000 which is unreachable from
            #  both this container and from OpenAI's servers)
            image_urls = []
            if raw_image_urls:
                data_uris = await asyncio.gather(
                    *[_download_image_as_data_uri(u) for u in raw_image_urls]
                )
                image_urls = [uri for uri in data_uris if uri is not None]
                logger.info(
                    "ticket %s: %d/%d images converted to base64",
                    tid, len(image_urls), len(raw_image_urls),
                )

            async with semaphore:
                try:
                    resp = await orchestrator.analyze(
                        ticket_id=tid,
                        description=description,
                        segment="Mass",
                        attachments=image_urls or None,
                        address_query=address_query,
                    )
                    return tid, resp, None
                except Exception as e:
                    logger.error("Analysis failed for ticket %s: %s", tid, e)
                    return tid, None, str(e)

        t_start = time.perf_counter()
        tasks = [_analyze_one(t) for t in pending]
        results = await asyncio.gather(*tasks)
        total_ms = (time.perf_counter() - t_start) * 1000

        # 5. Store successful analyses to DB
        stored = 0
        failed = 0
        errors: list[str] = []

        for tid, resp, err in results:
            if err or resp is None:
                failed += 1
                if err:
                    errors.append(f"{tid}: {err}")
                continue
            try:
                a = resp.analysis
                await bc.create_ticket_analysis(
                    ticket_id=resp.ticket_id,
                    request_type=a.request_type.value,
                    sentiment=a.sentiment.value,
                    urgency_score=a.urgency_score,
                    language=a.language.value,
                    summary=a.summary,
                    image_enriched=a.image_enriched,
                    latitude=a.geo.latitude,
                    longitude=a.geo.longitude,
                    formatted_address=a.geo.formatted_address,
                )
                stored += 1
                # Also save to local JSON
                await save_result(resp.model_dump())
            except Exception as e:
                failed += 1
                errors.append(f"{tid} (store): {e}")
                logger.warning("Failed to store analysis for %s: %s", tid, e)

        logger.info(
            "DB analyze run: %d stored, %d failed in %.1fms",
            stored, failed, total_ms,
        )

        return JSONResponse(
            content={
                "total_in_db": len(all_tickets),
                "already_analyzed": len(analyzed_ids),
                "processed": len(pending),
                "stored": stored,
                "failed": failed,
                "errors": errors[:50],  # cap error list
                "total_processing_ms": round(total_ms, 1),
            },
            media_type="application/json; charset=utf-8",
        )
    finally:
        await bc.close()


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
