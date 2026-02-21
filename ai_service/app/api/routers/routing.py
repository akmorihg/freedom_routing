"""Router: POST /routing/assign-from-db — run manager routing on analysed tickets."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.backend_client import BackendClient
from app.services.geo_client import GeoClient
from app.services.routing_service import RoutingService

logger = get_logger("router.routing")
router = APIRouter(prefix="/routing", tags=["Routing"])


@router.post(
    "/assign-from-db",
    status_code=status.HTTP_200_OK,
    summary="Route analysed tickets to managers",
    description=(
        "Fetches all ticket analyses and managers from the DB, runs the "
        "geo + load heuristic to assign each unassigned ticket to the "
        "best-scoring manager, and stores the assignments. "
        "Skips tickets that already have an assignment."
    ),
)
async def assign_from_db() -> JSONResponse:
    """Pull analyses + managers from DB → route → store assignments."""
    settings = get_settings()

    if not settings.google_maps_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_MAPS_API_KEY is required for office geocoding.",
        )

    bc = BackendClient(base_url=settings.backend_url, timeout=120.0)
    geo = GeoClient(api_key=settings.google_maps_api_key)

    try:
        svc = RoutingService(backend_client=bc, geo_client=geo)
        assignments = await svc.assign_all()

        return JSONResponse(
            content={
                "assigned": len(assignments),
                "assignments": [a.model_dump(mode="json") for a in assignments],
            },
            media_type="application/json; charset=utf-8",
        )
    except Exception:
        logger.exception("Routing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Routing failed unexpectedly. Check logs.",
        )
    finally:
        await bc.close()
