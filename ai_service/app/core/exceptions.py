"""Custom exception hierarchy for the AI analysis service."""

from __future__ import annotations


class AIServiceError(Exception):
    """Base exception for the AI analysis service."""


class LLMClientError(AIServiceError):
    """Raised when an LLM call fails after retries."""

    def __init__(self, task_name: str, detail: str = "") -> None:
        self.task_name = task_name
        self.detail = detail
        super().__init__(f"LLM task '{task_name}' failed: {detail}")


class LLMTimeoutError(LLMClientError):
    """Raised when an LLM call times out."""


class LLMValidationError(AIServiceError):
    """Raised when the raw LLM output fails post-processing validation."""

    def __init__(self, task_name: str, raw_output: str, reason: str = "") -> None:
        self.task_name = task_name
        self.raw_output = raw_output
        self.reason = reason
        super().__init__(
            f"Validation failed for task '{task_name}': {reason} (raw={raw_output!r})"
        )
