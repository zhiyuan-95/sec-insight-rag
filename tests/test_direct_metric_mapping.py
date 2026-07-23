from datetime import date
from decimal import Decimal

import pytest

from src.processing import (
    ArelleDiagnosticRecord,
    CompanyPrecedenceResult,
    ConceptIdentity,
    ConceptMetadataResolution,
    DirectConceptMapping,
    FactPrecedenceResolution,
    PrecedenceSelectedObservation,
    PrecedenceMetadataField,
    ReconciledObservation,
    ReconciliationSourceObservation,
    SemanticFactIdentity,
    canonical_metric_targets,
    map_precedence_selected_period,
)
from src.processing.inline_xbrl import INLINE_XBRL_SOURCE
from src.processing.observation_reconciliation import (
    RECONCILIATION_ARELLE_ONLY,
    RECONCILIATION_COMPANY_FACTS_ONLY,
)
from src.processing.xbrl_normalizer import NormalizedFact


def test_period_mapping_maps_precedence_selected_arelle_and_company_facts_observations() -> None:
    targets_by_name = {
        target.metric_name: target for target in canonical_metric_targets(())
    }
    gross_profit = targets_by_name["gross_profit"]
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="Revenues",
            source=INLINE_XBRL_SOURCE,
            period_type="duration",
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="Assets",
            source="sec_companyfacts",
            period_type="instant",
            start_date=None,
        ),
    )

    result = map_precedence_selected_period(
        precedence=precedence,
        fiscal_year=2025,
        fiscal_period="FY",
        targets=(
            targets_by_name["revenue"],
            targets_by_name["total_assets"],
            gross_profit,
        ),
    )

    mapped = {
        (metric.metric_name, metric.raw_fact_id, metric.accession_number)
        for metric in result.direct_metrics
    }
    assert ("revenue", 101, "0000000001-25-000001") in mapped
    assert ("total_assets", 102, "0000000001-25-000001") in mapped
    assert result.missing_targets == (gross_profit,)


def test_period_mapping_applies_an_approved_company_concept_mapping() -> None:
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=201,
            taxonomy="custom",
            concept="CustomerRevenueGross",
            source=INLINE_XBRL_SOURCE,
            period_type="duration",
        )
    )

    result = map_precedence_selected_period(
        precedence=precedence,
        fiscal_year=2025,
        fiscal_period="FY",
        targets=canonical_metric_targets(()),
        approved_mappings=(
            DirectConceptMapping(
                taxonomy="custom",
                concept="CustomerRevenueGross",
                metric_name="revenue",
                statement_type="income_statement",
                mapping_id=41,
            ),
        ),
    )

    assert [
        (metric.metric_name, metric.raw_fact_id)
        for metric in result.direct_metrics
    ] == [("revenue", 201)]
    assert "revenue" not in {
        target.metric_name for target in result.missing_targets
    }
    assert [
        (
            lineage.raw_fact_id,
            lineage.mapping_origin,
            lineage.mapping_id,
        )
        for lineage in result.direct_mapping_lineage
    ] == [(201, "approved", 41)]


def test_approved_mapping_must_target_the_applicable_statement() -> None:
    selected = _selected_observation(
        raw_fact_id=202,
        taxonomy="custom",
        concept="CustomerRevenueGross",
        source=INLINE_XBRL_SOURCE,
        period_type="duration",
    )
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )

    result = map_precedence_selected_period(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        targets=(revenue,),
        approved_mappings=(
            DirectConceptMapping(
                taxonomy="custom",
                concept="CustomerRevenueGross",
                metric_name="revenue",
                statement_type="balance_sheet",
                mapping_id=42,
            ),
        ),
    )

    assert result.direct_metrics == ()
    assert result.direct_mapping_lineage == ()
    assert result.missing_targets == (revenue,)


@pytest.mark.parametrize(
    ("fact_overrides", "blocking_diagnostic", "expected_reason"),
    [
        ({"value": None}, False, "numeric_value_unavailable"),
        ({"is_numeric": False}, False, "source_not_numeric"),
        ({"period_type": "instant", "start_date": None}, False, "incompatible_period_type"),
        ({"unit": "shares"}, False, "incompatible_unit_family"),
        ({"is_consolidated": False}, False, "unusable_dimensional_context"),
        ({}, True, "blocking_diagnostic"),
    ],
)
def test_period_mapping_rejects_each_minimal_compatibility_failure(
    fact_overrides: dict[str, object],
    blocking_diagnostic: bool,
    expected_reason: str,
) -> None:
    selected = _selected_observation(
        raw_fact_id=301,
        concept="Revenues",
        source=INLINE_XBRL_SOURCE,
        period_type=str(fact_overrides.get("period_type", "duration")),
        start_date=fact_overrides.get("start_date", date(2024, 9, 29)),
        unit=str(fact_overrides.get("unit", "USD")),
        value=fact_overrides.get("value", Decimal("100")),
        is_numeric=fact_overrides.get("is_numeric", True),
        is_consolidated=bool(fact_overrides.get("is_consolidated", True)),
        blocking_diagnostic=blocking_diagnostic,
    )

    result = map_precedence_selected_period(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        targets=canonical_metric_targets(()),
    )

    assert result.direct_metrics == ()
    assert [
        (rejection.raw_fact_id, rejection.metric_name, rejection.reason)
        for rejection in result.compatibility_rejections
    ] == [(301, "revenue", expected_reason)]
    assert "revenue" in {
        target.metric_name for target in result.missing_targets
    }


def test_shadow_inference_remains_separate_and_does_not_resolve_missing_target() -> None:
    selected = _selected_observation(
        raw_fact_id=401,
        taxonomy="custom",
        concept="CustomerRevenueGross",
        source=INLINE_XBRL_SOURCE,
        period_type="duration",
    )
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    metadata = ConceptMetadataResolution(
        identity=ConceptIdentity(
            taxonomy="custom",
            concept="CustomerRevenueGross",
        ),
        fields=(
            PrecedenceMetadataField(
                name="label",
                value="Customer revenue gross",
                source_system="arelle_structural",
                source_accession_number="0000000001-25-000001",
                source_filing_date=date(2025, 10, 31),
            ),
            PrecedenceMetadataField(
                name="description",
                value="Revenue recognized from customer contracts",
                source_system="arelle_structural",
                source_accession_number="0000000001-25-000001",
                source_filing_date=date(2025, 10, 31),
            ),
        ),
    )

    result = map_precedence_selected_period(
        precedence=_precedence_result(
            selected,
            concept_metadata=(metadata,),
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        targets=(revenue,),
    )

    assert result.direct_metrics == ()
    assert [
        (
            candidate.raw_fact_id,
            candidate.metric_name,
            candidate.match_method,
        )
        for candidate in result.shadow_candidates
    ] == [(401, "revenue", "arelle_lexical_shadow_v1")]
    assert result.shadow_candidates[0].score > 0
    assert result.shadow_candidates[0].evidence["candidate_is_authoritative"] is False
    assert result.missing_targets == (revenue,)


def test_shadow_inference_does_not_label_company_facts_metadata_as_arelle_evidence() -> None:
    selected = _selected_observation(
        raw_fact_id=402,
        taxonomy="custom",
        concept="CustomerRevenueGross",
        source="sec_companyfacts",
        period_type="duration",
    )
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    metadata = ConceptMetadataResolution(
        identity=ConceptIdentity(
            taxonomy="custom",
            concept="CustomerRevenueGross",
        ),
        fields=(
            PrecedenceMetadataField(
                name="label",
                value="Customer revenue gross",
                source_system="sec_companyfacts",
                source_accession_number="0000000001-25-000001",
                source_filing_date=date(2025, 10, 31),
            ),
        ),
    )

    result = map_precedence_selected_period(
        precedence=_precedence_result(
            selected,
            concept_metadata=(metadata,),
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        targets=(revenue,),
    )

    assert result.shadow_candidates == ()
    assert result.missing_targets == (revenue,)


def test_source_controlled_priority_resolves_a_concept_shared_by_two_targets() -> None:
    targets_by_name = {
        target.metric_name: target
        for target in canonical_metric_targets(
            ("Industrials", "Information Technology")
        )
    }
    deferred_revenue = targets_by_name["deferred_revenue_current"]
    contract_liabilities = targets_by_name["contract_liabilities_current"]
    selected = _selected_observation(
        raw_fact_id=501,
        concept="ContractWithCustomerLiabilityCurrent",
        source=INLINE_XBRL_SOURCE,
        period_type="instant",
        start_date=None,
    )

    result = map_precedence_selected_period(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        targets=(deferred_revenue, contract_liabilities),
    )

    assert [metric.metric_name for metric in result.direct_metrics] == [
        "deferred_revenue_current"
    ]
    assert result.missing_targets == (contract_liabilities,)


def _precedence_result(
    *selected: PrecedenceSelectedObservation,
    concept_metadata: tuple[ConceptMetadataResolution, ...] = (),
) -> CompanyPrecedenceResult:
    return CompanyPrecedenceResult(
        fact_resolutions=tuple(
            FactPrecedenceResolution(
                semantic_identity=item.semantic_identity,
                selected=item,
                candidates=(),
                invalid_candidates=(),
                quarantined_candidates=(),
                equivalent_candidates=(),
            )
            for item in selected
        ),
        statement_networks=(),
        concept_metadata=concept_metadata,
    )


def _selected_observation(
    *,
    raw_fact_id: int,
    taxonomy: str = "us-gaap",
    concept: str,
    source: str,
    period_type: str,
    start_date: date | None = date(2024, 9, 29),
    unit: str = "USD",
    value: Decimal | None = Decimal("100"),
    is_numeric: bool | None = True,
    is_consolidated: bool = True,
    blocking_diagnostic: bool = False,
) -> PrecedenceSelectedObservation:
    fact = NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy=taxonomy,
        concept=concept,
        label=concept,
        description=f"{concept} documentation",
        unit=unit,
        value_raw=str(value) if value is not None else None,
        value=value,
        start_date=start_date,
        end_date=date(2025, 9, 27),
        period_type=period_type,
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 10, 31),
        accession_number="0000000001-25-000001",
        frame=None,
        source=source,
        is_numeric=is_numeric,
        is_consolidated=is_consolidated,
    )
    source_observation = ReconciliationSourceObservation(
        raw_fact_id=raw_fact_id,
        fact=fact,
        arelle_fact_id=f"fact-{raw_fact_id}" if source == INLINE_XBRL_SOURCE else None,
    )
    identity = SemanticFactIdentity(
        cik=fact.cik,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        start_date=fact.start_date,
        end_date=fact.end_date,
        unit=fact.unit,
        dimensions=(),
        is_consolidated=fact.is_consolidated,
    )
    reconciliation = ReconciledObservation(
        semantic_identity=identity,
        outcome=(
            RECONCILIATION_ARELLE_ONLY
            if source == INLINE_XBRL_SOURCE
            else RECONCILIATION_COMPANY_FACTS_ONLY
        ),
        match_kind=None,
        selected=source_observation,
        source_observations=(source_observation,),
        blocking_diagnostics=(
            (
                ArelleDiagnosticRecord(
                    severity="error",
                    code="xbrl:error",
                    message="Fact failed validation",
                    fact_ids=(f"fact-{raw_fact_id}",),
                ),
            )
            if blocking_diagnostic
            else ()
        ),
    )
    return PrecedenceSelectedObservation(
        semantic_identity=identity,
        accession_number=fact.accession_number or "",
        filing_date=fact.filed_date or date.min,
        observation=source_observation,
        reconciliation=reconciliation,
    )
