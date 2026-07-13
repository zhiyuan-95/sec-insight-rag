from dataclasses import replace
from datetime import date
from decimal import Decimal

from src.processing.mapping_targets import (
    CanonicalMetricTarget,
    TargetConceptCandidate,
    canonical_metric_targets,
    missing_metric_targets,
)
from src.processing.xbrl_normalizer import NormalizedFact


def test_canonical_metric_targets_collapse_catalog_aliases_and_flags() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )

    assert revenue.statement_type == "income_statement"
    assert revenue.aliases == (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    )
    assert revenue.industry_labels == ("Common Base",)
    assert revenue.required_for_core is True
    assert revenue.required_for_specialized_indicators is False


def test_missing_metric_targets_accepts_only_usable_approved_mapping_facts() -> None:
    target = _target()
    fact = _fact()
    mappings = {("custom", "CustomerRevenueGross"): "revenue"}

    assert missing_metric_targets((fact,), (target,), mappings) == ()
    assert missing_metric_targets(
        (replace(fact, value=None),),
        (target,),
        mappings,
    ) == (target,)
    assert missing_metric_targets(
        (replace(fact, is_consolidated=False),),
        (target,),
        mappings,
    ) == (target,)


def _target() -> CanonicalMetricTarget:
    candidate = TargetConceptCandidate(
        taxonomy="us-gaap",
        concept="Revenues",
        metric_name="revenue",
        statement_type="income_statement",
        industry_labels=("Common Base",),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )
    return CanonicalMetricTarget(
        metric_name="revenue",
        statement_type="income_statement",
        aliases=("Revenues",),
        candidate_concepts=(candidate,),
        industry_labels=("Common Base",),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )


def _fact() -> NormalizedFact:
    return NormalizedFact(
        cik="0000001234",
        entity_name="Example Co.",
        taxonomy="custom",
        concept="CustomerRevenueGross",
        label="Customer revenue gross",
        description=None,
        unit="USD",
        value_raw="100",
        value=Decimal("100"),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2026, 2, 1),
        accession_number="0000001234-26-000001",
        frame=None,
        source="companyfacts",
        is_numeric=True,
    )
