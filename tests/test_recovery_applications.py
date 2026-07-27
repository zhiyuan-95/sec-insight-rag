import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.processing.accession_precedence import (
    CompanyPrecedenceResult,
    FactPrecedenceResolution,
    PrecedenceSelectedObservation,
)
from src.processing.observation_reconciliation import (
    RECONCILIATION_ARELLE_ONLY,
    ReconciledObservation,
    ReconciliationSourceObservation,
    SemanticFactIdentity,
)
from src.processing.arelle_evidence import ArelleDiagnosticRecord
from src.processing.recovery_applications import (
    AffirmativeZeroEvidence,
    RECOVERY_APPLICATION_INVALID,
    RECOVERY_APPLICATION_SUCCEEDED,
    apply_semantic_recommendation_to_period,
)
from src.processing.semantic_evidence import (
    SemanticConceptEvidence,
    SemanticEvidencePacket,
    SemanticTargetDefinition,
)
from src.processing.semantic_recommendations import (
    RECOMMENDATION_UNANIMOUS_FORMULA,
    RECOMMENDATION_UNANIMOUS_ZERO,
    SemanticJudgeIdentity,
    SemanticJudgeResponseRecord,
    SemanticRecommendationRecord,
    SemanticTargetComparison,
)
from src.processing.xbrl_normalizer import NormalizedFact


def test_shared_formula_is_applied_independently_with_mixed_accession_lineage() -> None:
    recommendation = _formula_recommendation()
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
        ),
        _selected_observation(
            raw_fact_id=201,
            concept="ServiceRevenue",
            value=Decimal("70"),
            fiscal_year=2025,
            accession_number="0000000001-26-000001",
            filing_date=date(2026, 1, 31),
        ),
    )

    successful = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )
    failed = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=precedence,
        period_id="FY-2025",
        fiscal_year=2025,
        fiscal_period="FY",
        expected_start_date=date(2025, 1, 1),
        expected_end_date=date(2025, 12, 31),
    )

    assert len(successful) == 1
    assert successful[0].status == RECOVERY_APPLICATION_SUCCEEDED
    assert successful[0].value_numeric == Decimal("100")
    assert successful[0].source_raw_fact_ids == (101, 102)
    assert successful[0].source_accession_numbers == (
        "0000000001-25-000001",
        "0000000001-25-000002",
    )
    assert tuple(
        (component.concept, component.operator, component.value_numeric)
        for component in successful[0].components
    ) == (
        ("ProductRevenue", "+", Decimal("40")),
        ("ServiceRevenue", "+", Decimal("60")),
    )

    assert len(failed) == 1
    assert failed[0].status == RECOVERY_APPLICATION_INVALID
    assert failed[0].value_numeric is None
    assert (
        failed[0].failure_reason
        == "component_fact_unavailable:custom:ProductRevenue"
    )


def test_zero_requires_cited_affirmative_arelle_evidence_for_the_period() -> None:
    recommendation = _zero_recommendation()
    evidence = AffirmativeZeroEvidence(
        company_id="0000000001",
        target_metric_name="revenue",
        statement_type="income_statement",
        evidence_id="concept-servicerevenue",
        taxonomy="custom",
        concept="ServiceRevenue",
        raw_fact_id=101,
        arelle_fact_id="fact-101",
        value_numeric=Decimal("0"),
        source_accession_number="0000000001-25-000001",
        source_system="inline_xbrl",
        fiscal_year=2024,
        fiscal_period="FY",
        unit="USD",
        period_type="duration",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        filing_date=date(2025, 1, 31),
        dimensions=(),
        is_consolidated=True,
    )
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("0"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        )
    )

    successful = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
        affirmative_zero_evidence=(evidence,),
    )
    unsupported = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=_precedence_result(),
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )
    wrong_unit_evidence = replace(evidence, unit="shares")
    wrong_unit = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=_precedence_result(
            _selected_observation(
                raw_fact_id=101,
                concept="ServiceRevenue",
                value=Decimal("0"),
                fiscal_year=2024,
                accession_number="0000000001-25-000001",
                filing_date=date(2025, 1, 31),
                unit="shares",
            )
        ),
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
        affirmative_zero_evidence=(wrong_unit_evidence,),
    )

    assert len(successful) == 1
    assert successful[0].status == RECOVERY_APPLICATION_SUCCEEDED
    assert successful[0].decision == "zero"
    assert successful[0].value_numeric == Decimal("0")
    assert successful[0].source_raw_fact_ids == (101,)
    assert successful[0].source_accession_numbers == (
        "0000000001-25-000001",
    )
    assert successful[0].zero_evidence == evidence

    assert len(unsupported) == 1
    assert unsupported[0].status == RECOVERY_APPLICATION_INVALID
    assert unsupported[0].value_numeric is None
    assert unsupported[0].failure_reason == "affirmative_zero_evidence_unavailable"
    assert wrong_unit[0].status == RECOVERY_APPLICATION_INVALID
    assert (
        wrong_unit[0].failure_reason
        == "affirmative_zero_evidence_unavailable"
    )


def test_formula_supports_subtraction_without_changing_component_lineage() -> None:
    recommendation = _formula_recommendation_with_operator(
        concept="ProductRevenue",
        operator="-",
    )
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
        ),
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=recommendation,
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )[0]

    assert application.status == RECOVERY_APPLICATION_SUCCEEDED
    assert application.value_numeric == Decimal("20")
    assert application.source_raw_fact_ids == (101, 102)


@pytest.mark.parametrize(
    ("product_overrides", "failure_reason"),
    [
        ({"unit": "EUR"}, "component_unit_incompatible"),
        (
            {"start_date": date(2024, 7, 1)},
            "component_actual_period_incompatible",
        ),
        (
            {"blocking_diagnostic": True},
            "component_blocking_diagnostic:custom:ProductRevenue",
        ),
    ],
)
def test_formula_rejects_incompatible_or_diagnostically_blocked_components(
    product_overrides: dict[str, object],
    failure_reason: str,
) -> None:
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
            **product_overrides,
        ),
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=_formula_recommendation(),
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )[0]

    assert application.status == RECOVERY_APPLICATION_INVALID
    assert application.value_numeric is None
    assert application.failure_reason == failure_reason
    if product_overrides.get("blocking_diagnostic"):
        blocked = next(
            component
            for component in application.components
            if component.concept == "ProductRevenue"
        )
        assert tuple(
            diagnostic.code
            for diagnostic in blocked.blocking_diagnostics
        ) == ("xbrl:blocking",)


def test_formula_components_must_match_the_requested_actual_period() -> None:
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
            start_date=date(2024, 7, 1),
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
            start_date=date(2024, 7, 1),
        ),
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=_formula_recommendation(),
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )[0]

    assert application.status == RECOVERY_APPLICATION_INVALID
    assert application.failure_reason == "component_actual_period_incompatible"


def test_zero_rejects_evidence_not_backed_by_the_precedence_selected_fact() -> None:
    evidence = AffirmativeZeroEvidence(
        company_id="0000000001",
        target_metric_name="revenue",
        statement_type="income_statement",
        evidence_id="concept-servicerevenue",
        taxonomy="custom",
        concept="ServiceRevenue",
        raw_fact_id=101,
        arelle_fact_id="fact-forged",
        value_numeric=Decimal("0"),
        source_accession_number="0000000001-25-000001",
        source_system="inline_xbrl",
        fiscal_year=2024,
        fiscal_period="FY",
        unit="USD",
        period_type="duration",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        filing_date=date(2025, 1, 31),
        dimensions=(),
        is_consolidated=True,
    )
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("0"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        )
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=_zero_recommendation(),
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
        affirmative_zero_evidence=(evidence,),
    )[0]

    assert application.status == RECOVERY_APPLICATION_INVALID
    assert application.failure_reason == "affirmative_zero_evidence_unavailable"


def test_formula_rejects_components_from_the_wrong_unit_family() -> None:
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
            unit="shares",
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
            unit="shares",
        ),
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=_formula_recommendation(),
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )[0]

    assert application.status == RECOVERY_APPLICATION_INVALID
    assert application.failure_reason == "component_unit_family_incompatible"


def test_formula_uses_the_only_candidate_in_the_requested_actual_period() -> None:
    precedence = _precedence_result(
        _selected_observation(
            raw_fact_id=100,
            concept="ServiceRevenue",
            value=Decimal("600"),
            fiscal_year=2024,
            accession_number="0000000001-25-000000",
            filing_date=date(2025, 1, 15),
            start_date=date(2023, 1, 1),
        ),
        _selected_observation(
            raw_fact_id=101,
            concept="ServiceRevenue",
            value=Decimal("60"),
            fiscal_year=2024,
            accession_number="0000000001-25-000001",
            filing_date=date(2025, 1, 31),
        ),
        _selected_observation(
            raw_fact_id=102,
            concept="ProductRevenue",
            value=Decimal("40"),
            fiscal_year=2024,
            accession_number="0000000001-25-000002",
            filing_date=date(2025, 2, 28),
        ),
    )

    application = apply_semantic_recommendation_to_period(
        recommendation=_formula_recommendation(),
        precedence=precedence,
        period_id="FY-2024",
        fiscal_year=2024,
        fiscal_period="FY",
        expected_start_date=date(2024, 1, 1),
        expected_end_date=date(2024, 12, 31),
    )[0]

    assert application.status == RECOVERY_APPLICATION_SUCCEEDED
    assert application.value_numeric == Decimal("100")
    assert application.source_raw_fact_ids == (101, 102)


def _formula_recommendation() -> SemanticRecommendationRecord:
    packet = SemanticEvidencePacket(
        schema_version="1",
        arelle_evidence_status="available",
        targets=(
            SemanticTargetDefinition(
                metric_name="revenue",
                statement_type="income_statement",
                aliases=("sales",),
                candidate_concepts=("us-gaap:Revenue",),
                industry_labels=(),
                required_for_core=True,
                required_for_specialized_indicators=False,
            ),
        ),
        concepts=(
            _concept_evidence("ServiceRevenue"),
            _concept_evidence("ProductRevenue"),
        ),
        relationships=(),
        formula_assertions=(),
        validations=(),
        content_sha256="packet-hash",
    )
    canonical = json.dumps(
        {
            "components": [
                {
                    "concept": "ProductRevenue",
                    "evidence_refs": ["concept-productrevenue"],
                    "operator": "+",
                    "taxonomy": "custom",
                },
                {
                    "concept": "ServiceRevenue",
                    "evidence_refs": ["concept-servicerevenue"],
                    "operator": "+",
                    "taxonomy": "custom",
                },
            ],
            "decision": "formula",
            "evidence_refs": [
                "concept-productrevenue",
                "concept-servicerevenue",
            ],
            "statement_type": "income_statement",
            "target_metric_name": "revenue",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    comparison = SemanticTargetComparison(
        target_metric_name="revenue",
        statement_type="income_statement",
        outcome=RECOMMENDATION_UNANIMOUS_FORMULA,
        judge_canonical_json=(canonical, canonical, canonical),
        unanimous_canonical_json=canonical,
    )
    judge = SemanticJudgeIdentity("test", "test-model")
    response = SemanticJudgeResponseRecord(
        judge=judge,
        response_status="completed",
        started_at="2026-07-27T12:00:00+00:00",
        completed_at="2026-07-27T12:00:01+00:00",
        response_json="{}",
        canonical_response_json=canonical,
        error="",
    )
    return SemanticRecommendationRecord(
        recommendation_request_id="semantic-recommendation:test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024", "FY-2025"),
        packet_content_sha256=packet.content_sha256,
        packet_json=packet.to_json(),
        prompt_version="semantic_recommendation_v1",
        judge_lineup=(judge, judge, judge),
        judge_responses=(response, response, response),
        target_comparisons=(comparison,),
        outcome=RECOMMENDATION_UNANIMOUS_FORMULA,
        created_at="2026-07-27T12:00:02+00:00",
    )


def _formula_recommendation_with_operator(
    *,
    concept: str,
    operator: str,
) -> SemanticRecommendationRecord:
    recommendation = _formula_recommendation()
    comparison = recommendation.target_comparisons[0]
    canonical = json.loads(comparison.unanimous_canonical_json or "{}")
    for component in canonical["components"]:
        if component["concept"] == concept:
            component["operator"] = operator
    canonical_json = json.dumps(
        canonical,
        separators=(",", ":"),
        sort_keys=True,
    )
    return replace(
        recommendation,
        target_comparisons=(
            replace(
                comparison,
                judge_canonical_json=(
                    canonical_json,
                    canonical_json,
                    canonical_json,
                ),
                unanimous_canonical_json=canonical_json,
            ),
        ),
    )


def _zero_recommendation() -> SemanticRecommendationRecord:
    packet = SemanticEvidencePacket(
        schema_version="1",
        arelle_evidence_status="available",
        targets=(
            SemanticTargetDefinition(
                metric_name="revenue",
                statement_type="income_statement",
                aliases=("sales",),
                candidate_concepts=("us-gaap:Revenue",),
                industry_labels=(),
                required_for_core=True,
                required_for_specialized_indicators=False,
            ),
        ),
        concepts=(_concept_evidence("ServiceRevenue"),),
        relationships=(),
        formula_assertions=(),
        validations=(),
        content_sha256="zero-packet-hash",
    )
    canonical = json.dumps(
        {
            "components": [],
            "decision": "zero",
            "evidence_refs": ["concept-servicerevenue"],
            "statement_type": "income_statement",
            "target_metric_name": "revenue",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    comparison = SemanticTargetComparison(
        target_metric_name="revenue",
        statement_type="income_statement",
        outcome=RECOMMENDATION_UNANIMOUS_ZERO,
        judge_canonical_json=(canonical, canonical, canonical),
        unanimous_canonical_json=canonical,
    )
    judge = SemanticJudgeIdentity("test", "test-model")
    response = SemanticJudgeResponseRecord(
        judge=judge,
        response_status="completed",
        started_at="2026-07-27T12:00:00+00:00",
        completed_at="2026-07-27T12:00:01+00:00",
        response_json="{}",
        canonical_response_json=canonical,
        error="",
    )
    return SemanticRecommendationRecord(
        recommendation_request_id="semantic-recommendation:zero-test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024",),
        packet_content_sha256=packet.content_sha256,
        packet_json=packet.to_json(),
        prompt_version="semantic_recommendation_v1",
        judge_lineup=(judge, judge, judge),
        judge_responses=(response, response, response),
        target_comparisons=(comparison,),
        outcome=RECOMMENDATION_UNANIMOUS_ZERO,
        created_at="2026-07-27T12:00:02+00:00",
    )


def _concept_evidence(concept: str) -> SemanticConceptEvidence:
    return SemanticConceptEvidence(
        evidence_id=f"concept-{concept.casefold()}",
        taxonomy="custom",
        concept=concept,
        label=concept,
        label_source_system="arelle_structural",
        documentation=f"{concept} documentation",
        documentation_source_system="arelle_structural",
        namespace_uri="https://example.com/custom",
        type_qname="xbrli:monetaryItemType",
        base_type="monetaryItemType",
        period_type="duration",
        balance="credit",
        is_numeric=True,
        is_abstract=False,
        references=(),
        source_systems=("arelle_structural",),
        source_evidence_ids=(f"arelle-{concept.casefold()}",),
        component_eligible=True,
    )


def _precedence_result(
    *selected: PrecedenceSelectedObservation,
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
        concept_metadata=(),
    )


def _selected_observation(
    *,
    raw_fact_id: int,
    concept: str,
    value: Decimal,
    fiscal_year: int,
    accession_number: str,
    filing_date: date,
    unit: str = "USD",
    start_date: date | None = None,
    blocking_diagnostic: bool = False,
) -> PrecedenceSelectedObservation:
    actual_start_date = start_date or date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    fact = NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="custom",
        concept=concept,
        label=concept,
        description=f"{concept} documentation",
        unit=unit,
        value_raw=str(value),
        value=value,
        start_date=actual_start_date,
        end_date=end_date,
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        form="10-K",
        filed_date=filing_date,
        accession_number=accession_number,
        frame=None,
        source="inline_xbrl",
        is_numeric=True,
        is_consolidated=True,
    )
    source = ReconciliationSourceObservation(
        raw_fact_id=raw_fact_id,
        fact=fact,
        arelle_fact_id=f"fact-{raw_fact_id}",
    )
    identity = SemanticFactIdentity(
        cik=fact.cik,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        start_date=fact.start_date,
        end_date=fact.end_date,
        unit=fact.unit,
        dimensions=(),
        is_consolidated=True,
    )
    reconciliation = ReconciledObservation(
        semantic_identity=identity,
        outcome=RECONCILIATION_ARELLE_ONLY,
        match_kind=None,
        selected=source,
        source_observations=(source,),
        blocking_diagnostics=(
            (
                ArelleDiagnosticRecord(
                    severity="error",
                    code="xbrl:blocking",
                    message="Component failed validation",
                    fact_ids=(f"fact-{raw_fact_id}",),
                ),
            )
            if blocking_diagnostic
            else ()
        ),
    )
    return PrecedenceSelectedObservation(
        semantic_identity=identity,
        accession_number=accession_number,
        filing_date=filing_date,
        observation=source,
        reconciliation=reconciliation,
    )
