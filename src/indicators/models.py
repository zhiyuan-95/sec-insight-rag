"""Domain models for deterministic derived financial indicators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


CALCULATED = "calculated"
SKIPPED = "skipped"


@dataclass(frozen=True)
class IndicatorDefinition:
    """Formula metadata for one supported derived indicator."""

    indicator_name: str
    formula_name: str
    formula_version: str
    formula_text: str
    required_metric_names: tuple[str, ...]
    output_unit: str
    period_type: str


@dataclass(frozen=True)
class IndicatorResult:
    """A calculated or skipped derived indicator with source traceability."""

    company_id: int
    indicator_name: str
    formula_name: str
    formula_version: str
    unit: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    value_numeric: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    filing_date: date | None = None
    source_metric_ids: tuple[int, ...] = ()
    source_raw_fact_ids: tuple[int, ...] = ()
    source_accession_numbers: tuple[str, ...] = ()
    is_active_window: bool = True
    calculation_status: str = CALCULATED
    skip_reason: str | None = None
