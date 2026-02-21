"""Router: CSV upload endpoints for managers, business units, and tickets data.

POST /data/upload-managers       → parse managers.csv
POST /data/upload-business-units → parse business_units.csv
POST /data/upload-tickets        → parse tickets.csv (preview only, no LLM)
POST /data/upload-all            → upload all 3 CSVs at once
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.services.csv_handler import (
    parse_csv,
    parse_managers_csv,
    parse_business_units_csv,
)

logger = get_logger("router.data")
router = APIRouter(prefix="/data", tags=["Data Upload"])


# ── helpers ──────────────────────────────────────────────────────────────

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


# ── managers ─────────────────────────────────────────────────────────────

@router.post(
    "/upload-managers",
    status_code=status.HTTP_200_OK,
    summary="Upload managers.csv",
    description="Parse managers CSV and return structured manager data ready for DB insertion.",
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

    logger.info("Managers uploaded: %d parsed, %d skipped", len(result.managers), result.skipped_rows)

    return JSONResponse(
        content={
            "file": file.filename,
            "total_rows": result.total_rows,
            "parsed": len(result.managers),
            "skipped_rows": result.skipped_rows,
            "errors": result.errors,
            "managers": [m.model_dump(mode="json") for m in result.managers],
        },
        media_type="application/json; charset=utf-8",
    )


# ── business units ───────────────────────────────────────────────────────

@router.post(
    "/upload-business-units",
    status_code=status.HTTP_200_OK,
    summary="Upload business_units.csv",
    description="Parse business units CSV and return structured office data ready for DB insertion.",
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

    logger.info("Business units uploaded: %d parsed, %d skipped", len(result.units), result.skipped_rows)

    return JSONResponse(
        content={
            "file": file.filename,
            "total_rows": result.total_rows,
            "parsed": len(result.units),
            "skipped_rows": result.skipped_rows,
            "errors": result.errors,
            "units": [u.model_dump(mode="json") for u in result.units],
        },
        media_type="application/json; charset=utf-8",
    )


# ── tickets (preview only) ──────────────────────────────────────────────

@router.post(
    "/upload-tickets",
    status_code=status.HTTP_200_OK,
    summary="Upload tickets.csv (parse only, no LLM)",
    description=(
        "Parse tickets CSV and return structured ticket data. "
        "Does NOT run AI analysis — use /ai/upload-csv for that."
    ),
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

    logger.info("Tickets uploaded: %d parsed, %d skipped", len(result.tickets), result.skipped_rows)

    return JSONResponse(
        content={
            "file": file.filename,
            "total_rows": result.total_rows,
            "parsed": len(result.tickets),
            "skipped_rows": result.skipped_rows,
            "errors": result.errors,
            "tickets": [t.model_dump(mode="json") for t in result.tickets],
        },
        media_type="application/json; charset=utf-8",
    )


# ── upload all 3 at once ────────────────────────────────────────────────

@router.post(
    "/upload-all",
    status_code=status.HTTP_200_OK,
    summary="Upload all 3 CSV files at once",
    description=(
        "Accepts tickets.csv, managers.csv, and business_units.csv in a single "
        "multipart request. Each file is identified by its form field name: "
        "'tickets', 'managers', 'business_units'."
    ),
)
async def upload_all(
    tickets: UploadFile = File(..., description="tickets.csv"),
    managers: UploadFile = File(..., description="managers.csv"),
    business_units: UploadFile = File(..., description="business_units.csv"),
) -> JSONResponse:
    """Parse all three CSV files and return combined result."""
    tickets_content = await _read_csv_file(tickets)
    managers_content = await _read_csv_file(managers)
    bu_content = await _read_csv_file(business_units)

    tickets_result = parse_csv(tickets_content)
    managers_result = parse_managers_csv(managers_content)
    bu_result = parse_business_units_csv(bu_content)

    logger.info(
        "Bulk upload: tickets=%d managers=%d units=%d",
        len(tickets_result.tickets),
        len(managers_result.managers),
        len(bu_result.units),
    )

    return JSONResponse(
        content={
            "tickets": {
                "file": tickets.filename,
                "total_rows": tickets_result.total_rows,
                "parsed": len(tickets_result.tickets),
                "skipped_rows": tickets_result.skipped_rows,
                "errors": tickets_result.errors,
                "data": [t.model_dump(mode="json") for t in tickets_result.tickets],
            },
            "managers": {
                "file": managers.filename,
                "total_rows": managers_result.total_rows,
                "parsed": len(managers_result.managers),
                "skipped_rows": managers_result.skipped_rows,
                "errors": managers_result.errors,
                "data": [m.model_dump(mode="json") for m in managers_result.managers],
            },
            "business_units": {
                "file": business_units.filename,
                "total_rows": bu_result.total_rows,
                "parsed": len(bu_result.units),
                "skipped_rows": bu_result.skipped_rows,
                "errors": bu_result.errors,
                "data": [u.model_dump(mode="json") for u in bu_result.units],
            },
        },
        media_type="application/json; charset=utf-8",
    )
