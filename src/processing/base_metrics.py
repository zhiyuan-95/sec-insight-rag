"""Map raw XBRL facts into business-friendly base financial metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.processing.active_window import ActivePeriodKey, is_fact_in_active_window
from src.processing.mapping_catalog import (
    IndustryFactTarget,
    mapping_candidates_by_concept,
    mapping_candidates_by_key,
)
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


BASE_METRIC_MAPPINGS: dict[str, IndustryFactTarget] = mapping_candidates_by_concept()
BASE_METRIC_MAPPINGS_BY_KEY: dict[tuple[str, str], IndustryFactTarget] = mapping_candidates_by_key()
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
    industry_labels: Iterable[str] | None = None,
    additional_mappings: Mapping[tuple[str, str], IndustryFactTarget] | None = None,
) -> list[BaseMetricRecord]:
    """Map clean supported raw XBRL facts into base metric records."""
    mappings = (
        BASE_METRIC_MAPPINGS_BY_KEY
        if industry_labels is None
        else mapping_candidates_by_key(industry_labels)
    )
    approved_mappings = additional_mappings or {}
    metrics: list[BaseMetricRecord] = []
    for raw_fact_id, fact in raw_facts:
        mapping = approved_mappings.get((fact.taxonomy, fact.concept)) or mappings.get(
            (fact.taxonomy, fact.concept)
        )
        if (
            mapping is None
            or not _is_usable_source_fact(fact)
            or (not fact.is_consolidated and mapping.consolidated_or_segment == "consolidated")
        ):
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
