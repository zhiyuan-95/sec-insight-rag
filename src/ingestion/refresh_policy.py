"""Refresh-date heuristics for SEC periodic filings."""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def next_check_date_for_filing(form_type: str, filing_date: date, fiscal_period: str | None = None) -> date:
    """Return the next local date when SEC submissions should be checked."""
    form = form_type.strip().upper()
    if form == "10-K":
        months = 12
    elif form == "10-Q":
        months = 6 if (fiscal_period or "").upper() == "Q3" else 3
    else:
        raise ValueError(f"Unsupported periodic filing form: {form_type}")
    return previous_business_day(add_months(filing_date, months))


def add_months(value: date, months: int) -> date:
    """Add calendar months while clamping to the target month's last day."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def previous_business_day(value: date) -> date:
    """Move weekend or market-holiday dates back to the prior open weekday."""
    while value.weekday() >= 5 or is_market_holiday(value):
        value -= timedelta(days=1)
    return value


def next_business_day(value: date) -> date:
    """Move weekend or market-holiday dates forward to the next open weekday."""
    while value.weekday() >= 5 or is_market_holiday(value):
        value += timedelta(days=1)
    return value


def is_market_holiday(value: date) -> bool:
    """Return whether the date is a standard US stock-market holiday."""
    holidays = _market_holidays(value.year - 1) | _market_holidays(value.year) | _market_holidays(value.year + 1)
    return value in holidays


def _market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _good_friday(year),
        _last_weekday(year, 5, 0),
        _observed_fixed_holiday(year, 7, 4),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed_fixed_holiday(year, 12, 25),
    }
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(year, 6, 19))
    return holidays


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    value = date(year, month, 1)
    days_until_weekday = (weekday - value.weekday()) % 7
    return value + timedelta(days=days_until_weekday + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    value = date(year, month, calendar.monthrange(year, month)[1])
    return value - timedelta(days=(value.weekday() - weekday) % 7)


def _good_friday(year: int) -> date:
    return _easter_sunday(year) - timedelta(days=2)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
