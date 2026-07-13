from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.processing.metric_recovery import (
    COMPONENT_ASSUMED_ZERO,
    COMPONENT_MAPPED,
    SKIP_DUPLICATE_COMPONENT_FACTS,
    SKIP_MISSING_REQUIRED_COMPONENT,
    SKIP_PERIOD_MISMATCH,
    SKIP_UNIT_MISMATCH,
    TARGET_DECOMPOSITION_INCOMPLETE,
    TARGET_DERIVED_FROM_COMPONENTS,
    TARGET_DIRECT_MAPPED,
    MetricRecoverySource,
    recover_debt_metrics,
)


def test_recover_debt_metrics_reports_direct_mapping() -> None:
    results = recover_debt_metrics([_metric("debt_current", "42", metric_id=1, raw_fact_id=11)])

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DIRECT_MAPPED
    assert current.value_numeric == Decimal("42")
    assert current.source_metric_ids == (1,)
    assert current.source_raw_fact_ids == (11,)
    assert current.formula_name is None


def test_recover_debt_metrics_derives_current_debt_from_components_with_optional_zero() -> None:
    results = recover_debt_metrics([_metric("long_term_debt_current", "50", metric_id=2, raw_fact_id=12)])

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DERIVED_FROM_COMPONENTS
    assert current.formula_name == "debt_current_components"
    assert current.value_numeric == Decimal("50")
    assert current.assumed_zero_components == (
        "short_term_borrowings",
        "current_finance_lease_debt",
    )
    statuses = {component.component_name: component.component_status for component in current.components}
    assert statuses["current_portion_of_long_term_debt"] == COMPONENT_MAPPED
    assert statuses["short_term_borrowings"] == COMPONENT_ASSUMED_ZERO


def test_recover_debt_metrics_derives_noncurrent_debt_from_combined_component() -> None:
    results = recover_debt_metrics(
        [
            _metric(
                "long_term_debt_and_finance_lease_obligations_noncurrent",
                "120",
                metric_id=3,
                raw_fact_id=13,
            )
        ]
    )

    noncurrent = _result(results, "debt_noncurrent")

    assert noncurrent.target_recovery_status == TARGET_DERIVED_FROM_COMPONENTS
    assert noncurrent.formula_name == "debt_noncurrent_combined_long_term_and_finance_lease"
    assert noncurrent.value_numeric == Decimal("120")
    assert noncurrent.source_metric_ids == (3,)


def test_recover_debt_metrics_skips_missing_required_component() -> None:
    results = recover_debt_metrics([_metric("short_term_borrowings", "5")])

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DECOMPOSITION_INCOMPLETE
    assert current.skip_reason == SKIP_MISSING_REQUIRED_COMPONENT
    assert "current_long_term_debt_and_finance_lease_obligations" in current.missing_required_components


def test_recover_debt_metrics_rejects_unit_mismatch() -> None:
    results = recover_debt_metrics(
        [
            _metric("long_term_debt_current", "50", unit="USD"),
            _metric("finance_lease_liability_current", "4", unit="EUR"),
        ]
    )

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DECOMPOSITION_INCOMPLETE
    assert current.skip_reason == SKIP_UNIT_MISMATCH


def test_recover_debt_metrics_rejects_duplicate_component_facts() -> None:
    results = recover_debt_metrics(
        [
            _metric("long_term_debt_current", "50", metric_id=4, raw_fact_id=14),
            _metric("long_term_debt_current", "55", metric_id=5, raw_fact_id=15),
        ]
    )

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DECOMPOSITION_INCOMPLETE
    assert current.skip_reason == SKIP_DUPLICATE_COMPONENT_FACTS
    assert current.source_metric_ids == (4, 5)
    assert current.source_raw_fact_ids == (14, 15)


def test_recover_debt_metrics_rejects_period_mismatch() -> None:
    results = recover_debt_metrics(
        [
            _metric("long_term_debt_current", "50", period_type="duration"),
            _metric("short_term_borrowings", "5", period_type="instant"),
        ]
    )

    current = _result(results, "debt_current")

    assert current.target_recovery_status == TARGET_DECOMPOSITION_INCOMPLETE
    assert current.skip_reason == SKIP_PERIOD_MISMATCH


def _result(results, target_metric_name: str):
    return next(result for result in results if result.target_metric_name == target_metric_name)


def _metric(
    metric_name: str,
    value: str,
    *,
    unit: str = "USD",
    period_type: str = "instant",
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    metric_id: int | None = None,
    raw_fact_id: int | None = None,
) -> MetricRecoverySource:
    return MetricRecoverySource(
        company_id=1,
        metric_name=metric_name,
        statement_type="balance_sheet",
        value_numeric=Decimal(value),
        unit=unit,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        accession_number="test-10k",
        metric_id=metric_id,
        raw_fact_id=raw_fact_id,
        end_date=date(2025, 12, 31),
        filing_date=date(2026, 2, 1),
    )
