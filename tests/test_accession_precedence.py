from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.processing import (
    ARELLE_RESULT_COMPLETE,
    RECONCILIATION_ARELLE_ONLY,
    RECONCILIATION_AMBIGUOUS_COMPANY_FACTS,
    AccessionReconciliationResult,
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleFilingIdentity,
    ArelleFilingResult,
    ArelleRecordCounts,
    ArelleRelationshipRecord,
    ArelleTimingRecord,
    NormalizedFact,
    ReconciledObservation,
    ReconciliationSourceObservation,
    SemanticFactIdentity,
    resolve_accession_precedence,
    select_compatible_components,
)
from src.processing.quality import DUPLICATE_FACT


def test_latest_valid_accession_wins_for_each_semantic_fact_identity() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
    )
    later = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-10-31",
        value="120",
    )

    result = resolve_accession_precedence((later, earlier))

    assert len(result.fact_resolutions) == 1
    resolution = result.fact_resolutions[0]
    assert resolution.selected is not None
    assert resolution.selected.accession_number == "0000320193-25-000001"
    assert resolution.selected.observation.fact.value == Decimal("120")
    assert tuple(
        candidate.accession_number for candidate in resolution.candidates
    ) == (
        "0000320193-24-000001",
        "0000320193-25-000001",
    )


def test_invalid_later_observation_does_not_erase_earlier_valid_value() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
    )
    invalid_later = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-10-31",
        value="120",
        usable=False,
    )

    result = resolve_accession_precedence((earlier, invalid_later))

    resolution = result.fact_resolutions[0]
    assert resolution.selected is not None
    assert resolution.selected.accession_number == "0000320193-24-000001"
    assert tuple(
        candidate.accession_number for candidate in resolution.invalid_candidates
    ) == ("0000320193-25-000001",)


def test_equivalent_cross_accession_duplicates_collapse_with_lineage() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
    )
    later = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-10-31",
        value="100.00",
    )

    result = resolve_accession_precedence((earlier, later))

    resolution = result.fact_resolutions[0]
    assert resolution.selected is not None
    assert resolution.selected.accession_number == "0000320193-25-000001"
    assert tuple(
        candidate.accession_number
        for candidate in resolution.equivalent_candidates
    ) == (
        "0000320193-24-000001",
        "0000320193-25-000001",
    )


def test_unresolved_same_accession_conflict_remains_quarantined() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
    )
    conflicting_later = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-10-31",
        value="120",
        usable=False,
        conflicting_duplicate=True,
    )

    result = resolve_accession_precedence((earlier, conflicting_later))

    resolution = result.fact_resolutions[0]
    assert resolution.selected is not None
    assert resolution.selected.accession_number == "0000320193-24-000001"
    assert tuple(
        candidate.accession_number
        for candidate in resolution.quarantined_candidates
    ) == ("0000320193-25-000001",)
    assert resolution.invalid_candidates == ()


def test_ambiguous_company_facts_candidate_remains_quarantined() -> None:
    ambiguous = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-10-31",
        value="120",
        usable=False,
        reconciliation_outcome=RECONCILIATION_AMBIGUOUS_COMPANY_FACTS,
        fact_source="sec_companyfacts",
    )

    result = resolve_accession_precedence((ambiguous,))

    resolution = result.fact_resolutions[0]
    assert resolution.selected is None
    assert resolution.invalid_candidates == ()
    assert tuple(
        candidate.accession_number
        for candidate in resolution.quarantined_candidates
    ) == ("0000320193-25-000001",)


def test_partial_amendment_updates_only_facts_it_reports() -> None:
    earlier = _combine_reconciliations(
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="Revenue",
            value="100",
        ),
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="OperatingExpense",
            value="60",
        ),
    )
    partial_amendment = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-01-15",
        concept="Revenue",
        value="110",
    )

    result = resolve_accession_precedence((earlier, partial_amendment))

    selected_by_concept = {
        selected.semantic_identity.concept: selected
        for selected in result.selected_observations
    }
    assert selected_by_concept["Revenue"].accession_number == (
        "0000320193-25-000001"
    )
    assert selected_by_concept["OperatingExpense"].accession_number == (
        "0000320193-24-000001"
    )


def test_partial_amendment_replaces_only_statement_networks_it_provides() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
        relationships=(
            _relationship(
                evidence_id="old-presentation",
                network_kind="presentation",
                arcrole="parent-child",
                link_role="income-statement",
            ),
            _relationship(
                evidence_id="old-calculation",
                network_kind="calculation",
                arcrole="summation-item",
                link_role="income-statement",
            ),
        ),
    )
    partial_amendment = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-01-15",
        value="110",
        relationships=(
            _relationship(
                evidence_id="new-presentation",
                network_kind="presentation",
                arcrole="parent-child",
                link_role="income-statement",
            ),
        ),
    )

    result = resolve_accession_precedence((partial_amendment, earlier))

    networks_by_kind = {
        network.identity.network_kind: network
        for network in result.statement_networks
    }
    assert networks_by_kind["presentation"].source_accession_number == (
        "0000320193-25-000001"
    )
    assert networks_by_kind["presentation"].relationships[0].evidence_id == (
        "new-presentation"
    )
    assert networks_by_kind["calculation"].source_accession_number == (
        "0000320193-24-000001"
    )


def test_blocked_amendment_network_does_not_erase_earlier_usable_network() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
        relationships=(
            _relationship(
                evidence_id="old-presentation",
                network_kind="presentation",
                arcrole="parent-child",
                link_role="income-statement",
            ),
        ),
    )
    blocked_relationship = _relationship(
        evidence_id="blocked-presentation",
        network_kind="presentation",
        arcrole="parent-child",
        link_role="income-statement",
    )
    amendment = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-01-15",
        value="110",
        relationships=(blocked_relationship,),
        diagnostics=(
            ArelleDiagnosticRecord(
                severity="error",
                code="xbrl:blocked-relationship",
                message="The amended relationship is unusable",
                relationship_ids=(blocked_relationship.evidence_id,),
            ),
        ),
    )

    result = resolve_accession_precedence((earlier, amendment))

    assert len(result.statement_networks) == 1
    selected_network = result.statement_networks[0]
    assert selected_network.source_accession_number == "0000320193-24-000001"
    assert selected_network.relationships[0].evidence_id == "old-presentation"


def test_concept_metadata_uses_field_level_amendment_precedence() -> None:
    earlier = _reconciliation(
        accession="0000320193-24-000001",
        filing_date="2024-10-31",
        value="100",
        concepts=(
            _concept(
                label="Revenue",
                documentation="Revenue from products and services",
            ),
        ),
    )
    amendment = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-01-15",
        value="110",
        concepts=(
            _concept(
                label="Net Revenue",
                documentation=None,
            ),
        ),
    )

    result = resolve_accession_precedence((amendment, earlier))

    assert len(result.concept_metadata) == 1
    fields = {
        field.name: field
        for field in result.concept_metadata[0].fields
    }
    assert fields["label"].value == "Net Revenue"
    assert fields["label"].source_accession_number == "0000320193-25-000001"
    assert fields["label"].source_system == "arelle_structural"
    assert fields["description"].value == "Revenue from products and services"
    assert fields["description"].source_accession_number == (
        "0000320193-24-000001"
    )
    assert fields["description"].source_system == "arelle_structural"


def test_compatible_components_can_retain_different_accession_lineage() -> None:
    earlier = _combine_reconciliations(
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="Revenue",
            value="100",
            raw_fact_id=11,
        ),
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="OperatingExpense",
            value="60",
            raw_fact_id=12,
        ),
    )
    partial_amendment = _reconciliation(
        accession="0000320193-25-000001",
        filing_date="2025-01-15",
        concept="Revenue",
        value="110",
        raw_fact_id=21,
    )
    result = resolve_accession_precedence((earlier, partial_amendment))
    identities_by_concept = {
        resolution.semantic_identity.concept: resolution.semantic_identity
        for resolution in result.fact_resolutions
    }

    components = select_compatible_components(
        result,
        (
            identities_by_concept["Revenue"],
            identities_by_concept["OperatingExpense"],
        ),
    )

    assert tuple(component.accession_number for component in components) == (
        "0000320193-25-000001",
        "0000320193-24-000001",
    )
    assert tuple(component.observation.raw_fact_id for component in components) == (
        21,
        12,
    )


def test_components_with_different_accounting_context_are_rejected() -> None:
    reconciliation = _combine_reconciliations(
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="Revenue",
            value="100",
            unit="USD",
        ),
        _reconciliation(
            accession="0000320193-24-000001",
            filing_date="2024-10-31",
            concept="EntityCommonStockSharesOutstanding",
            value="50",
            unit="SHARES",
        ),
    )
    result = resolve_accession_precedence((reconciliation,))

    with pytest.raises(ValueError, match="incompatible accounting contexts"):
        select_compatible_components(
            result,
            tuple(
                resolution.semantic_identity
                for resolution in result.fact_resolutions
            ),
        )


def _reconciliation(
    *,
    accession: str,
    filing_date: str,
    concept: str = "Revenue",
    value: str,
    raw_fact_id: int = 1,
    unit: str = "USD",
    usable: bool = True,
    conflicting_duplicate: bool = False,
    reconciliation_outcome: str = RECONCILIATION_ARELLE_ONLY,
    fact_source: str = "sec_inline_xbrl",
    relationships: tuple[ArelleRelationshipRecord, ...] = (),
    diagnostics: tuple[ArelleDiagnosticRecord, ...] = (),
    concepts: tuple[ArelleConceptRecord, ...] = (),
) -> AccessionReconciliationResult:
    fact = _fact(
        accession=accession,
        filing_date=filing_date,
        concept=concept,
        value=value,
        unit=unit,
        source=fact_source,
    )
    if conflicting_duplicate:
        fact = replace(fact, quality_flags=(DUPLICATE_FACT,))
    source_observation = ReconciliationSourceObservation(
        raw_fact_id=raw_fact_id,
        fact=fact,
    )
    identity = SemanticFactIdentity(
        cik=fact.cik,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        start_date=fact.start_date,
        end_date=fact.end_date,
        unit=fact.unit,
        dimensions=fact.dimensions,
        is_consolidated=fact.is_consolidated,
    )
    return AccessionReconciliationResult(
        observations=(
            ReconciledObservation(
                semantic_identity=identity,
                outcome=reconciliation_outcome,
                match_kind=None,
                selected=source_observation if usable else None,
                source_observations=(source_observation,),
                availability_markers=(
                    () if usable else ("arelle_fact_unavailable",)
                ),
            ),
        ),
        arelle_result=_arelle_result(
            accession=accession,
            filing_date=filing_date,
            relationships=relationships,
            diagnostics=diagnostics,
            concepts=concepts,
        ),
    )


def _fact(
    *,
    accession: str,
    filing_date: str,
    concept: str,
    value: str,
    unit: str,
    source: str,
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000320193",
        entity_name="Apple Inc.",
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        description=f"{concept} reported value",
        unit=unit,
        value_raw=value,
        value=Decimal(value),
        start_date=date(2023, 10, 1),
        end_date=date(2024, 9, 30),
        period_type="annual",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=date.fromisoformat(filing_date),
        accession_number=accession,
        frame="CY2024",
        source=source,
        namespace_uri="https://fasb.org/us-gaap/2024",
        context_id="duration-2024",
        source_document="filing.htm",
        balance="credit",
        is_numeric=True,
    )


def _combine_reconciliations(
    *reconciliations: AccessionReconciliationResult,
) -> AccessionReconciliationResult:
    first = reconciliations[0]
    return replace(
        first,
        observations=tuple(
            observation
            for reconciliation in reconciliations
            for observation in reconciliation.observations
        ),
    )


def _arelle_result(
    *,
    accession: str,
    filing_date: str,
    relationships: tuple[ArelleRelationshipRecord, ...] = (),
    diagnostics: tuple[ArelleDiagnosticRecord, ...] = (),
    concepts: tuple[ArelleConceptRecord, ...] = (),
) -> ArelleFilingResult:
    return ArelleFilingResult(
        schema_version="2",
        adapter_version="1",
        arelle_version="test",
        filing=ArelleFilingIdentity(
            cik="0000320193",
            accession_number=accession,
            form="10-K",
            filing_date=filing_date,
            entry_point_path="filing.htm",
            source_url="https://www.sec.gov/example/filing.htm",
        ),
        status=ARELLE_RESULT_COMPLETE,
        facts=(),
        concepts=concepts,
        contexts=(),
        units=(),
        relationships=relationships,
        formula_assertions=(),
        diagnostics=diagnostics,
        namespaces=(),
        source_documents=(),
        record_counts=ArelleRecordCounts(),
        timings=ArelleTimingRecord(),
        content_sha256=None,
        payload_sha256="",
        worker_pid=None,
        session_closed=True,
    )


def _relationship(
    *,
    evidence_id: str,
    network_kind: str,
    arcrole: str,
    link_role: str,
) -> ArelleRelationshipRecord:
    return ArelleRelationshipRecord(
        evidence_id=evidence_id,
        network_kind=network_kind,
        arcrole=arcrole,
        link_role=link_role,
        from_id="concept:Parent",
        to_id="concept:Child",
        order="1",
        weight=None,
        preferred_label=None,
        target_role=None,
    )


def _concept(
    *,
    label: str | None,
    documentation: str | None,
) -> ArelleConceptRecord:
    return ArelleConceptRecord(
        evidence_id="concept-revenue",
        qname="{https://fasb.org/us-gaap/2024}Revenue",
        namespace_uri="https://fasb.org/us-gaap/2024",
        local_name="Revenue",
        prefix="us-gaap",
        label=label,
        documentation=documentation,
        type_qname="{http://www.xbrl.org/2003/instance}monetaryItemType",
        base_type="monetaryItemType",
        period_type="duration",
        balance="credit",
        is_numeric=True,
        is_abstract=False,
    )
