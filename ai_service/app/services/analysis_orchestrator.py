"""Analysis orchestrator — launches all LLM tasks concurrently and
assembles the validated response.

Architecture:
  Phase 0 (optional): If attachments exist, describe images first to enrich text.
  Phase 1: Five LLM tasks + geo task run concurrently via ``asyncio.gather``.
  Phase 2: Collect results, validate, apply fallbacks, build response.

Each task handles its own retries, validation, and fallback internally.
One failed task never crashes the entire request.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.responses import (
    AnalysisMeta,
    AnalysisResult,
    AnalyzeTicketResponse,
    GeoCoordinates,
    RetriesUsed,
    TaskLatencies,
)
from app.services.geo_client import GeoClient
from app.services.llm_client import LLMClient
from app.services import prompt_registry as prompts
from app.services.tasks import (
    geo_task,
    image_describe_task,
    language_task,
    request_type_task,
    sentiment_task,
    summary_task,
    urgency_task,
)

logger = get_logger("orchestrator")


class AnalysisOrchestrator:
    """Facade that runs all analysis sub-tasks for a single ticket.

    Usage::

        orchestrator = AnalysisOrchestrator(settings)
        response = await orchestrator.analyze(ticket_id, description, ...)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm = LLMClient(settings)
        self._geo: GeoClient | None = None
        if settings.google_maps_api_key:
            self._geo = GeoClient(settings.google_maps_api_key)

    # ── public ───────────────────────────────────────────────────────────

    async def analyze(
        self,
        ticket_id: str,
        description: str,
        segment: str = "Mass",
        attachments: list[str] | None = None,
        address_query: str = "",
    ) -> AnalyzeTicketResponse:
        """Run all analysis tasks and return structured response."""
        attachments = attachments or []
        image_enriched = False
        img_retries = 0
        img_fb = False
        img_lat = 0.0

        logger.info(
            "analyze started ticket_id=%s text_len=%d attachments=%d segment=%s geo=%s",
            ticket_id,
            len(description),
            len(attachments),
            segment,
            bool(address_query),
        )
        t_start = time.perf_counter()

        # -- Phase 0: image enrichment (if attachments present) ----------------
        if attachments:
            img_t0 = time.perf_counter()
            img_text, img_retries, img_fb = await image_describe_task.run(
                self._llm,
                attachments,
                max_retries=self._settings.max_retries,
                timeout=self._settings.task_timeout_seconds + 3.0,
                base_delay=self._settings.retry_base_delay,
            )
            img_lat = (time.perf_counter() - img_t0) * 1000

            if img_text:
                enrichment = prompts.IMAGE_ENRICHMENT_PREFIX.format(
                    image_context=img_text,
                )
                if description.strip():
                    description = enrichment + description
                else:
                    description = img_text
                image_enriched = True
                logger.info(
                    "ticket_id=%s enriched with image context (%d chars)",
                    ticket_id,
                    len(img_text),
                )

        # Guard: if description is still empty after enrichment
        if not description.strip():
            description = "Обращение клиента без текста и без вложений."

        # Image URLs for multimodal LLM tasks
        task_images = attachments if attachments else None

        # -- Phase 1: launch all tasks concurrently ----------------------------
        (
            rt_result,
            sent_result,
            urg_result,
            lang_result,
            summ_result,
            geo_result,
        ) = await asyncio.gather(
            self._timed_llm_task("request_type", request_type_task.run, description, image_urls=task_images),
            self._timed_llm_task("sentiment", sentiment_task.run, description, image_urls=task_images),
            self._timed_llm_task("urgency_score", urgency_task.run, description, image_urls=task_images),
            self._timed_llm_task("language", language_task.run, description, image_urls=task_images),
            self._timed_llm_task("summary", summary_task.run, description, image_urls=task_images),
            self._timed_geo_task(address_query),
        )

        total_ms = (time.perf_counter() - t_start) * 1000

        # -- Unpack results (value, retries, fallback_used, latency_ms) --------
        request_type_val, rt_retries, rt_fb, rt_lat = rt_result
        sentiment_val, sent_retries, sent_fb, sent_lat = sent_result
        urgency_val, urg_retries, urg_fb, urg_lat = urg_result
        language_val, lang_retries, lang_fb, lang_lat = lang_result
        summary_val, summ_retries, summ_fb, summ_lat = summ_result
        geo_val, geo_retries, geo_fb, geo_lat = geo_result

        # -- Unpack geo tuple --------------------------------------------------
        geo_lat_coord, geo_lon_coord, geo_formatted, geo_status = geo_val

        # -- Collect fallback names -------------------------------------------
        fallbacks_used: list[str] = []
        if rt_fb:
            fallbacks_used.append("request_type")
        if sent_fb:
            fallbacks_used.append("sentiment")
        if urg_fb:
            fallbacks_used.append("urgency_score")
        if lang_fb:
            fallbacks_used.append("language")
        if summ_fb:
            fallbacks_used.append("summary")
        if geo_fb:
            fallbacks_used.append("geo")
        if img_fb:
            fallbacks_used.append("image_describe")

        # -- Assemble response ------------------------------------------------
        analysis = AnalysisResult(
            request_type=request_type_val,
            sentiment=sentiment_val,
            urgency_score=urgency_val,
            language=language_val,
            summary=summary_val,
            geo=GeoCoordinates(
                latitude=geo_lat_coord,
                longitude=geo_lon_coord,
                formatted_address=geo_formatted,
                geo_status=geo_status,
            ),
            image_enriched=image_enriched,
        )

        meta = AnalysisMeta(
            model=self._llm.model_name,
            task_latencies_ms=TaskLatencies(
                request_type=round(rt_lat, 1),
                sentiment=round(sent_lat, 1),
                urgency_score=round(urg_lat, 1),
                language=round(lang_lat, 1),
                summary=round(summ_lat, 1),
                geo=round(geo_lat, 1),
                image_describe=round(img_lat, 1),
            ),
            retries_used=RetriesUsed(
                request_type=rt_retries,
                sentiment=sent_retries,
                urgency_score=urg_retries,
                language=lang_retries,
                summary=summ_retries,
                geo=geo_retries,
                image_describe=img_retries,
            ),
            fallbacks_used=fallbacks_used,
            total_processing_ms=round(total_ms, 1),
        )

        logger.info(
            "analyze completed ticket_id=%s total_ms=%.1f fallbacks=%s image_enriched=%s",
            ticket_id,
            total_ms,
            fallbacks_used or "none",
            image_enriched,
        )

        return AnalyzeTicketResponse(
            ticket_id=ticket_id,
            analysis=analysis,
            meta=meta,
        )

    # ── internal helpers ─────────────────────────────────────────────────

    async def _timed_llm_task(
        self,
        name: str,
        task_fn: Any,
        description: str,
        *,
        image_urls: list[str] | None = None,
        **extra: Any,
    ) -> tuple[Any, int, bool, float]:
        """Run an LLM task function, measuring wall-clock time."""
        logger.debug("task %s starting", name)
        t0 = time.perf_counter()
        value, retries, fallback_used = await task_fn(
            self._llm,
            description,
            max_retries=self._settings.max_retries,
            timeout=self._settings.task_timeout_seconds,
            base_delay=self._settings.retry_base_delay,
            image_urls=image_urls,
            **extra,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "task %s done in %.1fms retries=%d fallback=%s",
            name,
            latency_ms,
            retries,
            fallback_used,
        )
        return value, retries, fallback_used, latency_ms

    async def _timed_geo_task(
        self,
        address_query: str,
    ) -> tuple[tuple[Any, ...], int, bool, float]:
        """Run the geo task, measuring wall-clock time."""
        if not self._geo or not address_query.strip():
            return (None, None, "", "skipped"), 0, False, 0.0

        logger.debug("task geo starting")
        t0 = time.perf_counter()
        value, retries, fallback_used = await geo_task.run(
            self._geo,
            address_query,
            max_retries=self._settings.max_retries,
            timeout=self._settings.task_timeout_seconds,
            base_delay=self._settings.retry_base_delay,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "task geo done in %.1fms retries=%d fallback=%s",
            latency_ms,
            retries,
            fallback_used,
        )
        return value, retries, fallback_used, latency_ms
