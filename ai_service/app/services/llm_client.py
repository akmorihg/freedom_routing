"""Thin async wrapper around the OpenAI chat-completion API.

Provides high-level helpers for each analysis task while keeping
the underlying HTTP transport pluggable.  Supports both text-only
and multimodal (vision) calls.
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
        image_urls: list[str] | None = None,
    ) -> str:
        """Send a chat completion request and return the raw text.

        If *image_urls* are provided, the user message is built as a
        multimodal content array (text + images) for GPT-4o-mini vision.
        """
        if image_urls:
            user_content: list[dict[str, Any]] = [
                {"type": "text", "text": user_prompt},
            ]
            for url in image_urls:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": url, "detail": "low"},
                })
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            max_tokens=max_tokens,
            messages=messages,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    # ── public task methods ──────────────────────────────────────────────

    async def classify_request_type(
        self, text: str, *, image_urls: list[str] | None = None,
    ) -> str:
        """Return raw model output for request-type classification."""
        return await self._complete(
            prompts.REQUEST_TYPE_SYSTEM,
            prompts.REQUEST_TYPE_USER.format(description=text),
            max_tokens=30,
            image_urls=image_urls,
        )

    async def classify_sentiment(
        self, text: str, *, image_urls: list[str] | None = None,
    ) -> str:
        """Return raw model output for sentiment classification."""
        return await self._complete(
            prompts.SENTIMENT_SYSTEM,
            prompts.SENTIMENT_USER.format(description=text),
            max_tokens=20,
            image_urls=image_urls,
        )

    async def estimate_urgency(
        self, text: str, *, image_urls: list[str] | None = None,
    ) -> str:
        """Return raw model output for urgency scoring."""
        return await self._complete(
            prompts.URGENCY_SYSTEM,
            prompts.URGENCY_USER.format(description=text),
            max_tokens=10,
            image_urls=image_urls,
        )

    async def detect_language(
        self, text: str, *, image_urls: list[str] | None = None,
    ) -> str:
        """Return raw model output for language detection."""
        return await self._complete(
            prompts.LANGUAGE_SYSTEM,
            prompts.LANGUAGE_USER.format(description=text),
            max_tokens=10,
            image_urls=image_urls,
        )

    async def summarize_ticket(
        self,
        text: str,
        context: dict[str, str] | None = None,
        *,
        image_urls: list[str] | None = None,
    ) -> str:
        """Return raw model output for ticket summarisation."""
        return await self._complete(
            prompts.SUMMARY_SYSTEM,
            prompts.SUMMARY_USER.format(description=text),
            max_tokens=200,
            image_urls=image_urls,
        )

    async def describe_image(self, image_urls: list[str]) -> str:
        """Describe attachment image(s) to enrich a ticket with no/short text.

        Returns a Russian-language description of what the screenshot shows.
        """
        return await self._complete(
            prompts.IMAGE_DESCRIBE_SYSTEM,
            prompts.IMAGE_DESCRIBE_USER,
            max_tokens=300,
            image_urls=image_urls,
        )

    @property
    def model_name(self) -> str:
        return self._model
