from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

MEXICO_CITY = ZoneInfo("America/Mexico_City")


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_utc_naive(dt: datetime) -> datetime:
    """SQL Server DATETIME2 columns store naive UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def mexico_local_to_utc(naive_local: datetime) -> datetime:
    return naive_local.replace(tzinfo=MEXICO_CITY).astimezone(UTC)
