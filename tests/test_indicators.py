from datetime import date
from decimal import Decimal

from src.indicators import calculate_indicators, formula_text, indicator_names
from src.indicators.engine import (
    MISSING_REQUIRED_METRIC,
    UNIT_MISMATCH,
    ZERO_DENOMINATOR,
)
from src.indicators.models import SKIPPED, IndicatorResult
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FinancialIndicatorRepository,
    FinancialMetric,
    connect_sqlite,
)


def test_indicator_catalog_is_unique_and_exposes_formula_text() -> None:
    names = indicator_names()

    assert len(names) == len(set(names))
    assert "free_cash_flow" in names
    assert formula_text("free_cash_flow") == (
        "operating_cash_flow - abs(capital_expenditure)"
    )


def test_indicator_engine_calculates_growth_margins_and_free_cash_flow_with_lineage() -> None:
    metrics = [
        _metric(1, "revenue", "100", 2024, metric_id=1, raw_fact_id=11, active=False),
        _metric(1, "revenue", "120", 2025, metric_id=2, raw_fact_id=12),
        _metric(1, "gross_profit", "72", 2025, metric_id=3, raw_fact_id=13),
        _metric(1, "operating_cash_flow", "30", 2025, metric_id=4, raw_fact_id=14),
        _metric(1, "capital_expenditure", "-10", 2025, metric_id=5, raw_fact_id=15),
    ]

    results = _results_by_name(calculate_indicators(1, metrics))

    assert results["revenue_growth_yoy"].value_numeric == Decimal("0.2")
    assert results["gross_margin"].value_numeric == Decimal("0.6")
    assert results["free_cash_flow"].value_numeric == Decimal("20")
    assert results["free_cash_flow"].unit == "USD"
    assert results["free_cash_flow"].source_metric_ids == (4, 5)
    assert results["free_cash_flow"].source_raw_fact_ids == (14, 15)
    assert results["free_cash_flow"].source_accession_numbers == (
        "accession-2025-capital_expenditure",
        "accession-2025-operating_cash_flow",
    )
    assert {result.fiscal_year for result in results.values()} == {2025}


def test_indicator_engine_returns_explicit_skip_reasons() -> None:
    zero_revenue = [
        _metric(1, "revenue", "0", 2025),
        _metric(1, "gross_profit", "10", 2025),
        _metric(1, "net_income", "5", 2025, unit="shares"),
    ]

    results = _results_by_name(calculate_indicators(1, zero_revenue))

    assert results["gross_margin"].calculation_status == SKIPPED
    assert results["gross_margin"].skip_reason == ZERO_DENOMINATOR
    assert results["net_margin"].skip_reason == UNIT_MISMATCH
    assert results["current_ratio"].skip_reason == MISSING_REQUIRED_METRIC


def test_indicator_engine_ignores_other_companies_and_can_emit_inactive_periods() -> None:
    metrics = [
        _metric(1, "revenue", "100", 2024, active=False),
        _metric(1, "revenue", "120", 2025),
        _metric(2, "revenue", "999", 2025),
    ]

    active_results = calculate_indicators(1, metrics)
    all_results = calculate_indicators(1, metrics, active_only=False)

    assert {result.fiscal_year for result in active_results} == {2025}
    assert {result.fiscal_year for result in all_results} == {2024, 2025}
    assert all(result.company_id == 1 for result in all_results)


def test_indicator_repository_round_trips_updates_filters_and_skips(tmp_path) -> None:
    with connect_sqlite(tmp_path / "indicators.db") as connection:
        repository = FinancialIndicatorRepository(connection)
        repository.initialize()
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(cik="0000000001", name="Test", ticker="TEST")
        )
        assert company.company_id is not None
        calculated = IndicatorResult(
            company_id=company.company_id,
            indicator_name="gross_margin",
            formula_name="gross_margin",
            formula_version="v1",
            value_numeric=Decimal("0.5"),
            unit="ratio",
            period_type="duration",
            fiscal_year=2025,
            fiscal_period="FY",
            source_metric_ids=(1, 2),
            source_raw_fact_ids=(11, 12),
            source_accession_numbers=("a", "b"),
        )
        skipped = IndicatorResult(
            company_id=company.company_id,
            indicator_name="current_ratio",
            formula_name="current_ratio",
            formula_version="v1",
            value_numeric=None,
            unit="ratio",
            period_type="instant",
            fiscal_year=2025,
            fiscal_period="FY",
            is_active_window=False,
            calculation_status=SKIPPED,
            skip_reason=MISSING_REQUIRED_METRIC,
        )

        assert repository.upsert_indicators([calculated, skipped]) == 2
        active = repository.list_indicators(company.company_id)
        all_rows = repository.list_indicators(company.company_id, active_only=False)

        assert active == [calculated]
        assert {row.indicator_name for row in all_rows} == {
            "gross_margin",
            "current_ratio",
        }
        updated = IndicatorResult(**{**calculated.__dict__, "value_numeric": Decimal("0.6")})
        repository.upsert_indicators([updated])
        assert repository.list_indicators(company.company_id)[0].value_numeric == Decimal("0.6")
        assert repository.deactivate_by_company_id(company.company_id) == 2
        assert repository.list_indicators(company.company_id) == []


def _results_by_name(results: list[IndicatorResult]) -> dict[str, IndicatorResult]:
    return {result.indicator_name: result for result in results}


def _metric(
    company_id: int,
    name: str,
    value: str,
    fiscal_year: int,
    *,
    metric_id: int | None = None,
    raw_fact_id: int | None = None,
    unit: str = "USD",
    active: bool = True,
) -> FinancialMetric:
    return FinancialMetric(
        metric_id=metric_id,
        company_id=company_id,
        accession_number=f"accession-{fiscal_year}-{name}",
        raw_fact_id=raw_fact_id,
        statement_type="test",
        metric_name=name,
        value_numeric=Decimal(value),
        value_raw=value,
        unit=unit,
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        start_date=date(fiscal_year - 1, 1, 1),
        end_date=date(fiscal_year, 1, 1),
        filing_date=date(fiscal_year, 2, 1),
        is_active_window=active,
    )
