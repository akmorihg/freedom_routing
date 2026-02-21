"""Post-processing validators and normalisers for LLM outputs.

Each helper receives a raw string from the model and returns
either a validated canonical value or raises ``ValueError``.
"""

from __future__ import annotations

import re

from app.schemas.enums import Language, RequestType, Sentiment

# ── Request type ─────────────────────────────────────────────────────────

# Build a lowercase→enum lookup that also handles common substrings
_REQUEST_TYPE_MAP: dict[str, RequestType] = {}
for _rt in RequestType:
    _REQUEST_TYPE_MAP[_rt.value.lower()] = _rt
# Extra aliases the model sometimes returns
_REQUEST_TYPE_MAP.update(
    {
        "жалоба": RequestType.COMPLAINT,
        "смена данных": RequestType.DATA_CHANGE,
        "консультация": RequestType.CONSULTATION,
        "претензия": RequestType.CLAIM,
        "неработоспособность": RequestType.APP_MALFUNCTION,
        "неработоспособность приложения": RequestType.APP_MALFUNCTION,
        "мошенничество": RequestType.FRAUD,
        "мошеннические действия": RequestType.FRAUD,
        "спам": RequestType.SPAM,
    }
)


def normalize_request_type(raw: str) -> RequestType:
    """Return a valid ``RequestType`` or raise ``ValueError``."""
    cleaned = raw.strip().strip('"').strip("'").strip(".").lower()
    result = _REQUEST_TYPE_MAP.get(cleaned)
    if result is not None:
        return result
    # Fuzzy substring match as last resort
    for key, val in _REQUEST_TYPE_MAP.items():
        if key in cleaned or cleaned in key:
            return val
    raise ValueError(f"Cannot map to RequestType: {raw!r}")


# ── Sentiment ────────────────────────────────────────────────────────────

_SENTIMENT_MAP: dict[str, Sentiment] = {
    "позитивный": Sentiment.POSITIVE,
    "положительный": Sentiment.POSITIVE,
    "positive": Sentiment.POSITIVE,
    "нейтральный": Sentiment.NEUTRAL,
    "neutral": Sentiment.NEUTRAL,
    "негативный": Sentiment.NEGATIVE,
    "отрицательный": Sentiment.NEGATIVE,
    "negative": Sentiment.NEGATIVE,
}


def normalize_sentiment(raw: str) -> Sentiment:
    """Return a valid ``Sentiment`` or raise ``ValueError``."""
    cleaned = raw.strip().strip('"').strip("'").strip(".").lower()
    result = _SENTIMENT_MAP.get(cleaned)
    if result is not None:
        return result
    for key, val in _SENTIMENT_MAP.items():
        if key in cleaned:
            return val
    raise ValueError(f"Cannot map to Sentiment: {raw!r}")


# ── Urgency ──────────────────────────────────────────────────────────────

_DIGIT_RE = re.compile(r"\d+")


def normalize_urgency(raw: str) -> int:
    """Return an integer 1..10 or raise ``ValueError``."""
    m = _DIGIT_RE.search(raw.strip())
    if m is None:
        raise ValueError(f"No integer found in urgency output: {raw!r}")
    value = int(m.group())
    if not 1 <= value <= 10:
        raise ValueError(f"Urgency {value} out of range 1..10")
    return value


# ── Language ─────────────────────────────────────────────────────────────

_LANGUAGE_MAP: dict[str, Language] = {
    "kz": Language.KZ,
    "kaz": Language.KZ,
    "kazakh": Language.KZ,
    "казахский": Language.KZ,
    "қазақша": Language.KZ,
    "eng": Language.ENG,
    "en": Language.ENG,
    "english": Language.ENG,
    "английский": Language.ENG,
    "ru": Language.RU,
    "rus": Language.RU,
    "russian": Language.RU,
    "русский": Language.RU,
}


def normalize_language(raw: str) -> Language:
    """Return a valid ``Language`` or raise ``ValueError``."""
    cleaned = raw.strip().strip('"').strip("'").strip(".").lower()
    result = _LANGUAGE_MAP.get(cleaned)
    if result is not None:
        return result
    for key, val in _LANGUAGE_MAP.items():
        if key in cleaned:
            return val
    raise ValueError(f"Cannot map to Language: {raw!r}")


# ── Summary ──────────────────────────────────────────────────────────────

def normalize_summary(raw: str) -> str:
    """Basic cleanup for summary text.  Raises on empty."""
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("Summary is empty")
    return cleaned
