from datetime import date

from src.processing import classify_period, parse_sec_date, validate_period
from src.processing.quality import INCONSISTENT_PERIOD, MISSING_END_DATE


def test_parse_sec_date_accepts_iso_date() -> None:
    assert parse_sec_date("2025-09-27") == date(2025, 9, 27)


def test_parse_sec_date_returns_none_for_missing_or_invalid_values() -> None:
    assert parse_sec_date(None) is None
    assert parse_sec_date("") is None
    assert parse_sec_date("not-a-date") is None


def test_classify_period_identifies_instant_duration_and_unknown() -> None:
    assert classify_period(None, date(2025, 9, 27)) == "instant"
    assert classify_period(date(2024, 9, 29), date(2025, 9, 27)) == "duration"
    assert classify_period(date(2024, 9, 29), None) == "unknown"


def test_validate_period_flags_missing_end_and_inconsistent_dates() -> None:
    assert validate_period(None, None) == (MISSING_END_DATE,)
    assert validate_period(date(2025, 9, 28), date(2025, 9, 27)) == (INCONSISTENT_PERIOD,)
