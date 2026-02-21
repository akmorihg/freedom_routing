"""Analysis orchestrator — launches all LLM tasks concurrently and
assembles the validated response.

Architecture:
  1. Four independent tasks (request_type, sentiment, urgency, language) run
     concurrently via ``asyncio.gather``.
  2. Summary task runs in parallel with the first group (can be moved to
     sequential if enrichment is needed later).
  3. Each task handles its own retries, validation, and fallback.
  4. Orchestrator collects results, builds response models, records metadata.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.schemas.enums import Language, RequestType, Sentiment
from app.schemas.responses import (
    AnalysisMeta,
    AnalysisResult,
    AnalyzeTicketResponse,
    RetriesUsed,
    TaskLatencies,
)
from app.services.llm_client import LLMClient
from app.services.tasks import (
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
        response = await orchestrator.analyze(ticket_id, description, segment)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm = LLMClient(settings)

    # ── public ───────────────────────────────────────────────────────────

    async def analyze(
        self,
        ticket_id: str,
        description: str,
        segment: str = "Mass",
    ) -> AnalyzeTicketResponse:
        """Run all analysis tasks and return structured response."""
        logger.info(
            "analyze started ticket_id=%s text_len=%d segment=%s",
            ticket_id,
            len(description),
            segment,
        )
        t_start = time.perf_counter()

        # -- launch all five tasks concurrently --------------------------------
        (
            rt_result,
            sent_result,
            urg_result,
            lang_result,
            summ_result,
        ) = await asyncio.gather(
            self._timed_task("request_type", request_type_task.run, description),
            self._timed_task("sentiment", sentiment_task.run, description),
            self._timed_task("urgency_score", urgency_task.run, description),
            self._timed_task("language", language_task.run, description),
            self._timed_task("summary", summary_task.run, description),
        )

        total_ms = (time.perf_counter() - t_start) * 1000

        # -- unpack results (value, retries, fallback_used, latency_ms) --------
        request_type_val, rt_retries, rt_fb, rt_lat = rt_result
        sentiment_val, sent_retries, sent_fb, sent_lat = sent_result
        urgency_val, urg_retries, urg_fb, urg_lat = urg_result
        language_val, lang_retries, lang_fb, lang_lat = lang_result
        summary_val, summ_retries, summ_fb, summ_lat = summ_result

        # -- collect fallback names -------------------------------------------
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

        # -- assemble response ------------------------------------------------
        analysis = AnalysisResult(
            request_type=request_type_val,
            sentiment=sentiment_val,
            urgency_score=urgency_val,
            language=language_val,
            summary=summary_val,
        )

        meta = AnalysisMeta(
            model=self._llm.model_name,
            task_latencies_ms=TaskLatencies(
                request_type=round(rt_lat, 1),
                sentiment=round(sent_lat, 1),
                urgency_score=round(urg_lat, 1),
                language=round(lang_lat, 1),
                summary=round(summ_lat, 1),
            ),
            retries_used=RetriesUsed(
                request_type=rt_retries,
                sentiment=sent_retries,
                urgency_score=urg_retries,
                language=lang_retries,
                summary=summ_retries,
            ),
            fallbacks_used=fallbacks_used,
            total_processing_ms=round(total_ms, 1),
        )

        logger.info(
            "analyze completed ticket_id=%s total_ms=%.1f fallbacks=%s",
            ticket_id,
            total_ms,
            fallbacks_used or "none",
        )

        return AnalyzeTicketResponse(
            ticket_id=ticket_id,
            analysis=analysis,
            meta=meta,
        )

    # ── internal helpers ─────────────────────────────────────────────────

    async def _timed_task(
        self,
        name: str,
        task_fn: Any,
        description: str,
        **extra: Any,
    ) -> tuple[Any, int, bool, float]:
        """Run a single task function, measuring wall-clock time.

        Returns (value, retries_used, fallback_used, latency_ms).
        """
        logger.debug("task %s starting", name)
        t0 = time.perf_counter()
        value, retries, fallback_used = await task_fn(
            self._llm,
            description,
            max_retries=self._settings.max_retries,
            timeout=self._settings.task_timeout_seconds,
            base_delay=self._settings.retry_base_delay,
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
