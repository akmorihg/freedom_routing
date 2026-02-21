"""Tests for core validation / normalisation helpers and fallback logic."""

from __future__ import annotations

import asyncio

import pytest

from app.core.validation import (
    normalize_language,
    normalize_request_type,
    normalize_sentiment,
    normalize_summary,
    normalize_urgency,
)
from app.schemas.enums import Language, RequestType, Sentiment


# ━━━━━━━━━━━━━━━━━━━ Request Type ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeRequestType:
    """Validate that various model outputs normalise to exact enum values."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Жалоба", RequestType.COMPLAINT),
            ("жалоба", RequestType.COMPLAINT),
            (" Жалоба\n", RequestType.COMPLAINT),
            ('"Жалоба"', RequestType.COMPLAINT),
            ("Смена данных", RequestType.DATA_CHANGE),
            ("смена данных", RequestType.DATA_CHANGE),
            ("Консультация", RequestType.CONSULTATION),
            ("Претензия", RequestType.CLAIM),
            ("Неработоспособность приложения", RequestType.APP_MALFUNCTION),
            ("Неработоспособность", RequestType.APP_MALFUNCTION),
            ("Мошеннические действия", RequestType.FRAUD),
            ("мошенничество", RequestType.FRAUD),
            ("Спам", RequestType.SPAM),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: RequestType) -> None:
        assert normalize_request_type(raw) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_request_type("абракадабра")


# ━━━━━━━━━━━━━━━━━━━ Sentiment ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeSentiment:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Позитивный", Sentiment.POSITIVE),
            ("позитивный", Sentiment.POSITIVE),
            ("Положительный", Sentiment.POSITIVE),
            ("positive", Sentiment.POSITIVE),
            ("Нейтральный", Sentiment.NEUTRAL),
            ("neutral", Sentiment.NEUTRAL),
            ("Негативный", Sentiment.NEGATIVE),
            ("negative", Sentiment.NEGATIVE),
            ("Отрицательный", Sentiment.NEGATIVE),
            (" негативный. ", Sentiment.NEGATIVE),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: Sentiment) -> None:
        assert normalize_sentiment(raw) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_sentiment("фиолетовый")


# ━━━━━━━━━━━━━━━━━━━ Urgency ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeUrgency:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("5", 5),
            (" 7 ", 7),
            ("10", 10),
            ("1", 1),
            ("urgency: 8", 8),
            ("3/10", 3),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: int) -> None:
        assert normalize_urgency(raw) == expected

    @pytest.mark.parametrize("raw", ["0", "11", "abc", ""])
    def test_invalid_raises(self, raw: str) -> None:
        with pytest.raises(ValueError):
            normalize_urgency(raw)


# ━━━━━━━━━━━━━━━━━━━ Language ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeLanguage:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("RU", Language.RU),
            ("ru", Language.RU),
            ("русский", Language.RU),
            ("Russian", Language.RU),
            ("ENG", Language.ENG),
            ("en", Language.ENG),
            ("English", Language.ENG),
            ("английский", Language.ENG),
            ("KZ", Language.KZ),
            ("kaz", Language.KZ),
            ("казахский", Language.KZ),
            ("қазақша", Language.KZ),
        ],
    )
    def test_valid_inputs(self, raw: str, expected: Language) -> None:
        assert normalize_language(raw) == expected

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_language("Martian")


# ━━━━━━━━━━━━━━━━━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNormalizeSummary:
    def test_strips_whitespace(self) -> None:
        assert normalize_summary("  Привет мир  ") == "Привет мир"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_summary("   ")


# ━━━━━━━━━━━━━━━━━━━ Retry wrapper ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRetryWithTimeout:
    """Integration-style tests for retry_with_timeout."""

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        from app.core.retry import retry_with_timeout

        async def _ok() -> str:
            return "ok"

        result, retries = await retry_with_timeout(
            _ok, task_name="test", max_retries=2, timeout_seconds=1.0
        )
        assert result == "ok"
        assert retries == 0

    @pytest.mark.asyncio
    async def test_succeeds_on_retry(self) -> None:
        from app.core.retry import retry_with_timeout

        call_count = 0

        async def _fail_then_ok() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("boom")
            return "recovered"

        result, retries = await retry_with_timeout(
            _fail_then_ok,
            task_name="test",
            max_retries=2,
            timeout_seconds=1.0,
            base_delay=0.01,
        )
        assert result == "recovered"
        assert retries == 1

    @pytest.mark.asyncio
    async def test_all_attempts_fail_raises(self) -> None:
        from app.core.retry import retry_with_timeout

        async def _always_fail() -> str:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await retry_with_timeout(
                _always_fail,
                task_name="test",
                max_retries=1,
                timeout_seconds=1.0,
                base_delay=0.01,
            )

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self) -> None:
        from app.core.retry import retry_with_timeout

        call_count = 0

        async def _slow_then_fast() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                await asyncio.sleep(5)
            return "fast"

        result, retries = await retry_with_timeout(
            _slow_then_fast,
            task_name="test",
            max_retries=2,
            timeout_seconds=0.1,
            base_delay=0.01,
        )
        assert result == "fast"
        assert retries == 1


# ━━━━━━━━━━━━━━━━━━━ Schema validation ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestResponseSchemas:
    """Ensure Pydantic models accept valid data and reject bad data."""

    def test_analysis_result_valid(self) -> None:
        from app.schemas.responses import AnalysisResult

        result = AnalysisResult(
            request_type=RequestType.COMPLAINT,
            sentiment=Sentiment.NEGATIVE,
            urgency_score=8,
            language=Language.RU,
            summary="Клиент жалуется. Рекомендуется связаться.",
        )
        assert result.urgency_score == 8

    def test_urgency_out_of_range(self) -> None:
        from pydantic import ValidationError
        from app.schemas.responses import AnalysisResult

        with pytest.raises(ValidationError):
            AnalysisResult(
                request_type=RequestType.COMPLAINT,
                sentiment=Sentiment.NEGATIVE,
                urgency_score=15,
                language=Language.RU,
                summary="test",
            )
