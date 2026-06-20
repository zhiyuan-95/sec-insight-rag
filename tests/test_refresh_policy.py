from datetime import date

from src.ingestion.refresh_policy import (
    is_market_holiday,
    next_business_day,
    next_check_date_for_filing,
    previous_business_day,
)


def test_previous_business_day_moves_weekends_and_market_holidays_back() -> None:
    assert previous_business_day(date(2026, 7, 4)) == date(2026, 7, 2)
    assert previous_business_day(date(2026, 4, 3)) == date(2026, 4, 2)


def test_next_business_day_moves_weekends_and_market_holidays_forward() -> None:
    assert next_business_day(date(2026, 7, 4)) == date(2026, 7, 6)
    assert next_business_day(date(2026, 12, 25)) == date(2026, 12, 28)


def test_next_check_date_for_filing_uses_market_open_day() -> None:
    assert next_check_date_for_filing("10-K", date(2025, 7, 3)) == date(2026, 7, 2)
    assert next_check_date_for_filing("10-Q", date(2025, 12, 25), "Q1") == date(2026, 3, 25)


def test_is_market_holiday_recognizes_observed_fixed_holiday() -> None:
    assert is_market_holiday(date(2026, 7, 3))
