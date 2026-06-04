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
    """Move Saturday/Sunday dates back to Friday."""
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value
