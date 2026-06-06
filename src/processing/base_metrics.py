"""Map raw XBRL facts into business-friendly base financial metrics."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.processing.active_window import ActivePeriodKey, is_fact_in_active_window
from src.processing.quality import (
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    MISSING_ACCESSION_NUMBER,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
)
from src.processing.xbrl_normalizer import NormalizedFact


@dataclass(frozen=True)
class BaseMetricMapping:
    """Statement and metric name for one supported XBRL concept."""

    statement_type: str
    metric_name: str


@dataclass(frozen=True)
class BaseMetricRecord:
    """A deterministic base metric mapped from one raw XBRL fact."""

    raw_fact_id: int
    accession_number: str
    statement_type: str
    metric_name: str
    value_numeric: Decimal | None
    value_raw: object
    unit: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    start_date: date | None
    end_date: date | None
    filing_date: date | None
    is_active_window: bool


BASE_METRIC_MAPPINGS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": BaseMetricMapping("income_statement", "revenue"),
    "Revenues": BaseMetricMapping("income_statement", "revenue"),
    "CostOfRevenue": BaseMetricMapping("income_statement", "cost_of_revenue"),
    "GrossProfit": BaseMetricMapping("income_statement", "gross_profit"),
    "OperatingIncomeLoss": BaseMetricMapping("income_statement", "operating_income"),
    "NetIncomeLoss": BaseMetricMapping("income_statement", "net_income"),
    "CashAndCashEquivalentsAtCarryingValue": BaseMetricMapping("balance_sheet", "cash_and_equivalents"),
    "Assets": BaseMetricMapping("balance_sheet", "total_assets"),
    "AssetsCurrent": BaseMetricMapping("balance_sheet", "current_assets"),
    "Liabilities": BaseMetricMapping("balance_sheet", "total_liabilities"),
    "LiabilitiesCurrent": BaseMetricMapping("balance_sheet", "current_liabilities"),
    "StockholdersEquity": BaseMetricMapping("balance_sheet", "shareholders_equity"),
    "NetCashProvidedByUsedInOperatingActivities": BaseMetricMapping("cash_flow_statement", "operating_cash_flow"),
    "PaymentsToAcquirePropertyPlantAndEquipment": BaseMetricMapping("cash_flow_statement", "capital_expenditure"),
}
SKIPPED_QUALITY_FLAGS = {
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    MISSING_ACCESSION_NUMBER,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
}


def map_raw_facts_to_base_metrics(
    raw_facts: Iterable[tuple[int, NormalizedFact]],
    active_keys: set[ActivePeriodKey],
) -> list[BaseMetricRecord]:
    """Map clean supported raw XBRL facts into base metric records."""
    metrics: list[BaseMetricRecord] = []
    for raw_fact_id, fact in raw_facts:
        mapping = BASE_METRIC_MAPPINGS.get(fact.concept)
        if mapping is None or not _is_usable_source_fact(fact):
            continue
        metrics.append(
            BaseMetricRecord(
                raw_fact_id=raw_fact_id,
                accession_number=fact.accession_number,
                statement_type=mapping.statement_type,
                metric_name=mapping.metric_name,
                value_numeric=fact.value,
                value_raw=fact.value_raw,
                unit=fact.unit,
                period_type=fact.period_type,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period,
                start_date=fact.start_date,
                end_date=fact.end_date,
                filing_date=fact.filed_date,
                is_active_window=is_fact_in_active_window(fact, active_keys),
            )
        )
    return metrics


def _is_usable_source_fact(fact: NormalizedFact) -> bool:
    if fact.accession_number is None or fact.form is None:
        return False
    if any(flag in SKIPPED_QUALITY_FLAGS for flag in fact.quality_flags):
        return False
    return fact.value is not None
