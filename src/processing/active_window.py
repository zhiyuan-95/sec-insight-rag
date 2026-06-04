"""Active analysis window helpers for stored SEC/XBRL data."""

from __future__ import annotations

from collections.abc import Iterable

from src.processing.xbrl_normalizer import NormalizedFact

ANNUAL_FORM = "10-K"
QUARTERLY_FORM = "10-Q"
ANNUAL_PERIOD = "FY"
ANNUAL_WINDOW_LIMIT = 5
QUARTERLY_WINDOW_LIMIT = 12
QUARTER_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
ActivePeriodKey = tuple[str, int, str]


def active_period_keys(
    facts: Iterable[NormalizedFact],
    *,
    annual_limit: int = ANNUAL_WINDOW_LIMIT,
    quarterly_limit: int = QUARTERLY_WINDOW_LIMIT,
) -> set[ActivePeriodKey]:
    """Return active latest 10-K fiscal years and 10-Q fiscal quarters."""
    annual_periods: set[tuple[int, str]] = set()
    quarterly_periods: set[tuple[int, str]] = set()
    for fact in facts:
        if fact.fiscal_year is None or fact.fiscal_period is None or fact.form is None:
            continue
        form = fact.form.upper()
        fiscal_period = fact.fiscal_period.upper()
        if form == ANNUAL_FORM and fiscal_period == ANNUAL_PERIOD:
            annual_periods.add((fact.fiscal_year, fiscal_period))
        elif form == QUARTERLY_FORM and fiscal_period in QUARTER_ORDER:
            quarterly_periods.add((fact.fiscal_year, fiscal_period))

    latest_annual = sorted(annual_periods, key=lambda item: item[0], reverse=True)[:annual_limit]
    latest_quarterly = sorted(
        quarterly_periods,
        key=lambda item: (item[0], QUARTER_ORDER[item[1]]),
        reverse=True,
    )[:quarterly_limit]
    active: set[ActivePeriodKey] = set()
    active.update(("10-K", fiscal_year, fiscal_period) for fiscal_year, fiscal_period in latest_annual)
    active.update(("10-Q", fiscal_year, fiscal_period) for fiscal_year, fiscal_period in latest_quarterly)
    return active


def is_fact_in_active_window(fact: NormalizedFact, active_keys: set[ActivePeriodKey]) -> bool:
    """Return whether a normalized fact belongs to the active analysis window."""
    if fact.form is None or fact.fiscal_year is None or fact.fiscal_period is None:
        return False
    return (fact.form.upper(), fact.fiscal_year, fact.fiscal_period.upper()) in active_keys


def active_accessions_for_facts(
    facts: Iterable[NormalizedFact],
    active_keys: set[ActivePeriodKey],
) -> set[str]:
    """Return accessions that have at least one fact in the active analysis window."""
    return {
        fact.accession_number
        for fact in facts
        if fact.accession_number and is_fact_in_active_window(fact, active_keys)
    }
