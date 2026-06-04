from datetime import date
from decimal import Decimal

from src.processing import (
    active_period_keys,
    map_raw_facts_to_base_metrics,
)
from src.processing.quality import AMBIGUOUS_UNIT, DUPLICATE_FACT
from src.processing.xbrl_normalizer import NormalizedFact


def test_active_period_keys_defaults_to_latest_five_annual_and_twelve_quarterly_periods() -> None:
    facts = [
        _fact(concept="Revenues", fiscal_year=year, fiscal_period="FY", form="10-K")
        for year in range(2020, 2027)
    ]
    facts.extend(
        _fact(concept="Revenues", fiscal_year=year, fiscal_period=quarter, form="10-Q")
        for year in range(2023, 2027)
        for quarter in ("Q1", "Q2", "Q3", "Q4")
    )

    active = active_period_keys(facts)

    assert ("10-K", 2026, "FY") in active
    assert ("10-K", 2022, "FY") in active
    assert ("10-K", 2021, "FY") not in active
    assert ("10-Q", 2026, "Q4") in active
    assert ("10-Q", 2024, "Q1") in active
    assert ("10-Q", 2023, "Q4") not in active


def test_map_raw_facts_to_base_metrics_maps_clean_facts_and_skips_ambiguous_sources() -> None:
    facts = [
        (1, _fact(concept="Revenues", fiscal_year=2025, fiscal_period="FY", form="10-K")),
        (2, _fact(concept="Assets", fiscal_year=2025, fiscal_period="FY", form="10-K")),
        (
            3,
            _fact(
                concept="NetCashProvidedByUsedInOperatingActivities",
                fiscal_year=2025,
                fiscal_period="FY",
                form="10-K",
            ),
        ),
        (
            4,
            _fact(
                concept="PaymentsToAcquirePropertyPlantAndEquipment",
                fiscal_year=2025,
                fiscal_period="FY",
                form="10-K",
            ),
        ),
        (
            5,
            _fact(
                concept="Revenues",
                fiscal_year=2025,
                fiscal_period="Q3",
                form="10-Q",
                quality_flags=(DUPLICATE_FACT,),
            ),
        ),
        (
            6,
            _fact(
                concept="Assets",
                fiscal_year=2025,
                fiscal_period="Q3",
                form="10-Q",
                quality_flags=(AMBIGUOUS_UNIT,),
            ),
        ),
    ]
    active = active_period_keys([fact for _, fact in facts])

    metrics = map_raw_facts_to_base_metrics(facts, active)

    metric_keys = {(metric.statement_type, metric.metric_name) for metric in metrics}
    assert metric_keys == {
        ("income_statement", "revenue"),
        ("balance_sheet", "total_assets"),
        ("cash_flow_statement", "operating_cash_flow"),
        ("cash_flow_statement", "capital_expenditure"),
    }
    assert {metric.raw_fact_id for metric in metrics} == {1, 2, 3, 4}
    assert all(metric.is_active_window for metric in metrics)
    assert "free_cash_flow" not in {metric.metric_name for metric in metrics}
    assert "total_debt" not in {metric.metric_name for metric in metrics}


def _fact(
    *,
    concept: str,
    fiscal_year: int,
    fiscal_period: str,
    form: str,
    quality_flags: tuple[str, ...] = (),
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000320193",
        entity_name="Apple Inc.",
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=date(fiscal_year - 1, 9, 29),
        end_date=date(fiscal_year, 9, 27),
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=date(fiscal_year, 10, 31),
        accession_number=f"0000320193-{str(fiscal_year)[-2:]}-000079-{fiscal_period}",
        frame=None,
        source="sec_companyfacts",
        quality_flags=quality_flags,
    )
