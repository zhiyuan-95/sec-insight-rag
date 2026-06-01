"""Date and period helpers for SEC XBRL facts."""

from __future__ import annotations

from datetime import date

from src.processing.quality import INCONSISTENT_PERIOD, MISSING_END_DATE


def parse_sec_date(value: object) -> date | None:
    """Parse SEC ISO date strings, returning None for missing or invalid values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def classify_period(start_date: date | None, end_date: date | None) -> str:
    """Classify an XBRL fact period."""
    if end_date is None:
        return "unknown"
    if start_date is None:
        return "instant"
    return "duration"


def validate_period(start_date: date | None, end_date: date | None) -> tuple[str, ...]:
    """Return quality flags for period problems."""
    flags: list[str] = []
    if end_date is None:
        flags.append(MISSING_END_DATE)
    if start_date is not None and end_date is not None and start_date > end_date:
        flags.append(INCONSISTENT_PERIOD)
    return tuple(flags)
