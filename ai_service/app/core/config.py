"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable application settings.

    All values are read from environment variables at construction time.
    Defaults are tuned for hackathon demo (low latency, predictable output).
    """

    # ── OpenAI ───────────────────────────────────────────────────────────
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    openai_temperature: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
    )
    openai_base_url: str | None = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", None)
    )

    # ── Retry / timeout (per-task) ───────────────────────────────────────
    task_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("TASK_TIMEOUT_SECONDS", "5.0"))
    )
    image_task_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("IMAGE_TASK_TIMEOUT_SECONDS", "45.0"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "2"))
    )
    retry_base_delay: float = field(
        default_factory=lambda: float(os.getenv("RETRY_BASE_DELAY", "0.3"))
    )

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_text_max_chars: int = field(
        default_factory=lambda: int(os.getenv("LOG_TEXT_MAX_CHARS", "100"))
    )

    # ── Google Maps (geo-normalization) ──────────────────────────────────
    google_maps_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_MAPS_API_KEY", "")
    )

    # ── Batch processing ─────────────────────────────────────────────────
    batch_max_concurrency: int = field(
        default_factory=lambda: int(os.getenv("BATCH_MAX_CONCURRENCY", "10"))
    )

    # ── Backend API (DB service) ─────────────────────────────────────────
    backend_url: str = field(
        default_factory=lambda: os.getenv("BACKEND_URL", "http://backend:8000")
    )

    # ── Service ──────────────────────────────────────────────────────────
    service_name: str = "ai-analysis-service"
    service_version: str = "0.1.0"


def get_settings() -> Settings:
    """Factory that returns a fresh ``Settings`` instance."""
    return Settings()
