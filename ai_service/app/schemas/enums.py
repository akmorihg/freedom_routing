"""Strict enums for analysis fields.

Keep enum *values* exactly as required by the downstream contract —
display labels are in Russian / upper-case codes.
"""

from __future__ import annotations

from enum import Enum


class RequestType(str, Enum):
    """Allowed ticket request types (Russian labels)."""

    COMPLAINT = "Жалоба"
    DATA_CHANGE = "Смена данных"
    CONSULTATION = "Консультация"
    CLAIM = "Претензия"
    APP_MALFUNCTION = "Неработоспособность приложения"
    FRAUD = "Мошеннические действия"
    SPAM = "Спам"


class Sentiment(str, Enum):
    """Sentiment labels."""

    POSITIVE = "Позитивный"
    NEUTRAL = "Нейтральный"
    NEGATIVE = "Негативный"


class Language(str, Enum):
    """Detected language codes."""

    KZ = "KZ"
    ENG = "ENG"
    RU = "RU"


class Segment(str, Enum):
    """Client segment (informational / future use)."""

    MASS = "Mass"
    VIP = "VIP"
    PRIORITY = "Priority"
