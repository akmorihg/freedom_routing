"""Thin async wrapper around the OpenAI chat-completion API.

Provides high-level helpers for each analysis task while keeping
the underlying HTTP transport pluggable.
"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.logging import get_logger
from app.services import prompt_registry as prompts

logger = get_logger("llm_client")


class LLMClient:
    """Reusable, async LLM client for the analysis service.

    Each public method corresponds to one analysis task (classification,
    detection, summarisation).  Internally all methods call ``_complete``
    which wraps the OpenAI async client.
    """

    def __init__(self, settings: Settings) -> None:
        self._model = settings.openai_model
        self._temperature = settings.openai_temperature
        client_kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        self._client = AsyncOpenAI(**client_kwargs)

    # ── internal ─────────────────────────────────────────────────────────

    async def _complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 120,
    ) -> str:
        """Send a chat completion request and return the raw text.

        No retry/timeout logic here — that is handled by the orchestrator
        layer via ``retry_with_timeout``.
        """
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    # ── public task methods ──────────────────────────────────────────────

    async def classify_request_type(self, text: str) -> str:
        """Return raw model output for request-type classification."""
        return await self._complete(
            prompts.REQUEST_TYPE_SYSTEM,
            prompts.REQUEST_TYPE_USER.format(description=text),
            max_tokens=30,
        )

    async def classify_sentiment(self, text: str) -> str:
        """Return raw model output for sentiment classification."""
        return await self._complete(
            prompts.SENTIMENT_SYSTEM,
            prompts.SENTIMENT_USER.format(description=text),
            max_tokens=20,
        )

    async def estimate_urgency(self, text: str) -> str:
        """Return raw model output for urgency scoring."""
        return await self._complete(
            prompts.URGENCY_SYSTEM,
            prompts.URGENCY_USER.format(description=text),
            max_tokens=10,
        )

    async def detect_language(self, text: str) -> str:
        """Return raw model output for language detection."""
        return await self._complete(
            prompts.LANGUAGE_SYSTEM,
            prompts.LANGUAGE_USER.format(description=text),
            max_tokens=10,
        )

    async def summarize_ticket(
        self, text: str, context: dict[str, str] | None = None,
    ) -> str:
        """Return raw model output for ticket summarisation."""
        # ``context`` reserved for future enrichment (e.g. known type/language)
        return await self._complete(
            prompts.SUMMARY_SYSTEM,
            prompts.SUMMARY_USER.format(description=text),
            max_tokens=200,
        )

    @property
    def model_name(self) -> str:
        return self._model
