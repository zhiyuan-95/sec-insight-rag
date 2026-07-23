from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.processing import (
    ARELLE_RESULT_COMPLETE,
    RECONCILIATION_ARELLE_ONLY,
    RECONCILIATION_AMBIGUOUS_COMPANY_FACTS,
    RECONCILIATION_COMPANY_FACTS_ONLY,
    RECONCILIATION_COMPANY_FACTS_REPLACEMENT,
    RECONCILIATION_CONFLICTING,
    RECONCILIATION_MATCHED,
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleFilingIdentity,
    ArelleFilingResult,
    ArelleRecordCounts,
    ArelleTimingRecord,
    NormalizedFact,
    ReconciliationSourceObservation,
    reconcile_accession_observations,
)
from src.processing.quality import AMBIGUOUS_UNIT, DUPLICATE_FACT, MISSING_VALUE


ACCESSION = "0000320193-25-000001"


def test_reconcile_accession_observations_matches_and_prefers_arelle() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw=100),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    assert len(result.observations) == 1
    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_MATCHED
    assert reconciled.match_kind == "exact"
    assert reconciled.selected == arelle
    assert reconciled.semantic_identity.taxonomy == "us-gaap"
    assert reconciled.semantic_identity.concept == "Revenue"
    assert reconciled.semantic_identity.unit == "USD"


def test_reconcile_accession_observations_records_conflict_and_keeps_arelle() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=200),
            value=Decimal("200"),
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_CONFLICTING
    assert reconciled.selected == arelle
    assert reconciled.source_observations == (arelle, company_facts)


def test_reconcile_accession_observations_classifies_source_only_facts() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=500),
            concept="Assets",
            label="Assets",
            description="Total assets",
            start_date=None,
            period_type="instant",
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    outcomes_by_raw_fact_id = {
        observation.selected.raw_fact_id: observation.outcome
        for observation in result.observations
        if observation.selected is not None
    }
    assert outcomes_by_raw_fact_id == {
        1: RECONCILIATION_ARELLE_ONLY,
        2: RECONCILIATION_COMPANY_FACTS_ONLY,
    }


def test_reconcile_accession_observations_quarantines_ambiguous_company_facts() -> None:
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            quality_flags=(DUPLICATE_FACT,),
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (company_facts,),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_AMBIGUOUS_COMPANY_FACTS
    assert reconciled.selected is None
    assert reconciled.source_observations == (company_facts,)


def test_reconcile_accession_observations_replaces_blocked_arelle_fact() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw=100),
    )
    blocker = ArelleDiagnosticRecord(
        severity="error",
        code="xbrl.4.6.2:numericFact",
        message="Arelle rejected this numeric fact",
        fact_ids=("fact-revenue",),
    )

    result = reconcile_accession_observations(
        _arelle_result(diagnostics=(blocker,)),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_COMPANY_FACTS_REPLACEMENT
    assert reconciled.selected == company_facts
    assert reconciled.availability_markers == ("arelle_fact_blocked",)
    assert reconciled.blocking_diagnostics == (blocker,)


def test_company_facts_supplement_retains_arelle_structural_evidence() -> None:
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw=100),
    )
    concept = ArelleConceptRecord(
        evidence_id="concept-revenue",
        qname="{https://fasb.org/us-gaap/2025}Revenue",
        namespace_uri="https://fasb.org/us-gaap/2025",
        local_name="Revenue",
        prefix="us-gaap",
        label="Revenue",
        documentation="Revenue recognized from customers",
        type_qname="{http://www.xbrl.org/2003/instance}monetaryItemType",
        base_type="monetaryItemType",
        period_type="duration",
        balance="credit",
        is_numeric=True,
        is_abstract=False,
    )
    arelle_result = _arelle_result(concepts=(concept,))

    result = reconcile_accession_observations(
        arelle_result,
        (company_facts,),
    )

    reconciled = result.observations[0]
    assert reconciled.selected == company_facts
    assert reconciled.availability_markers == ("arelle_fact_unavailable",)
    assert result.arelle_result is arelle_result
    assert result.arelle_result.concepts == (concept,)
    metadata = {
        field.name: (field.value, field.source)
        for field in reconciled.metadata
    }
    assert metadata["label"] == ("Revenue", "arelle_structural")
    assert metadata["description"] == (
        "Revenue recognized from customers",
        "arelle_structural",
    )


def test_reconciliation_metadata_prefers_arelle_and_attributes_filled_fields() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=replace(
            _fact(source="sec_inline_xbrl", value_raw=100),
            label="Arelle Revenue",
            description=None,
        ),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            label="Company Facts Revenue",
            description="Company Facts description",
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    metadata = {
        field.name: (field.value, field.source)
        for field in result.observations[0].metadata
    }
    assert metadata["label"] == ("Arelle Revenue", "sec_inline_xbrl")
    assert metadata["description"] == (
        "Company Facts description",
        "sec_companyfacts",
    )


def test_reconciliation_uses_company_facts_when_arelle_value_is_unusable() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=replace(
            _fact(source="sec_inline_xbrl", value_raw=100),
            value_raw=None,
            value=None,
            quality_flags=(MISSING_VALUE,),
        ),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw=100),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_COMPANY_FACTS_REPLACEMENT
    assert reconciled.selected == company_facts
    assert reconciled.availability_markers == ("arelle_fact_unavailable",)


def test_reconciliation_does_not_use_ambiguous_company_facts_as_replacement() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            quality_flags=(DUPLICATE_FACT,),
        ),
    )
    blocker = ArelleDiagnosticRecord(
        severity="error",
        code="xbrl.4.6.2:numericFact",
        message="Arelle rejected this numeric fact",
        fact_ids=("fact-revenue",),
    )

    result = reconcile_accession_observations(
        _arelle_result(diagnostics=(blocker,)),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_AMBIGUOUS_COMPANY_FACTS
    assert reconciled.selected is None
    assert reconciled.availability_markers == (
        "arelle_fact_blocked",
        "company_facts_ambiguous",
    )
    assert reconciled.blocking_diagnostics == (blocker,)


def test_reconciliation_rejects_observations_from_another_accession() -> None:
    wrong_accession = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            accession_number="0000320193-24-000001",
        ),
    )

    with pytest.raises(ValueError, match="one selected accession"):
        reconcile_accession_observations(
            _arelle_result(),
            (wrong_accession,),
        )


def test_ambiguous_company_facts_does_not_quarantine_valid_arelle() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            quality_flags=(DUPLICATE_FACT,),
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_AMBIGUOUS_COMPANY_FACTS
    assert reconciled.selected == arelle
    assert reconciled.availability_markers == ("company_facts_ambiguous",)


def test_source_only_unusable_observations_are_not_selected() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=replace(
            _fact(source="sec_inline_xbrl", value_raw=100),
            value_raw=None,
            value=None,
            quality_flags=(MISSING_VALUE,),
        ),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            value_raw=None,
            value=None,
            quality_flags=(MISSING_VALUE,),
        ),
    )

    arelle_only = reconcile_accession_observations(
        _arelle_result(),
        (arelle,),
    ).observations[0]
    company_facts_only = reconcile_accession_observations(
        _arelle_result(),
        (company_facts,),
    ).observations[0]

    assert arelle_only.outcome == RECONCILIATION_ARELLE_ONLY
    assert arelle_only.selected is None
    assert arelle_only.availability_markers == ("arelle_fact_unavailable",)
    assert company_facts_only.outcome == RECONCILIATION_COMPANY_FACTS_ONLY
    assert company_facts_only.selected is None
    assert company_facts_only.availability_markers == (
        "arelle_fact_unavailable",
        "company_facts_unusable",
    )


def test_blocked_arelle_only_observation_is_not_selected() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    blocker = ArelleDiagnosticRecord(
        severity="error",
        code="xbrl.4.6.2:numericFact",
        message="Arelle rejected this numeric fact",
        fact_ids=("fact-revenue",),
    )

    result = reconcile_accession_observations(
        _arelle_result(diagnostics=(blocker,)),
        (arelle,),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_ARELLE_ONLY
    assert reconciled.selected is None
    assert reconciled.availability_markers == ("arelle_fact_blocked",)
    assert reconciled.blocking_diagnostics == (blocker,)


def test_company_facts_with_ambiguous_unit_is_quarantined() -> None:
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            quality_flags=(AMBIGUOUS_UNIT,),
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (company_facts,),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_AMBIGUOUS_COMPANY_FACTS
    assert reconciled.selected is None
    assert reconciled.availability_markers == (
        "arelle_fact_unavailable",
        "company_facts_ambiguous",
    )


def test_reconciliation_recognizes_numerically_equivalent_values() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw="100.00"),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_MATCHED
    assert reconciled.match_kind == "numeric_equivalent"
    assert reconciled.selected == arelle


def test_reconciliation_conflict_does_not_block_unrelated_supplement() -> None:
    arelle_revenue = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=_fact(source="sec_inline_xbrl", value_raw=100),
        arelle_fact_id="fact-revenue",
    )
    company_facts_revenue = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=_fact(source="sec_companyfacts", value_raw=200),
    )
    company_facts_assets = ReconciliationSourceObservation(
        raw_fact_id=3,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=500),
            concept="Assets",
            label="Assets",
            description="Total assets",
            start_date=None,
            period_type="instant",
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle_revenue, company_facts_revenue, company_facts_assets),
    )

    by_concept = {
        observation.semantic_identity.concept: observation
        for observation in result.observations
    }
    assert by_concept["Revenue"].outcome == RECONCILIATION_CONFLICTING
    assert by_concept["Revenue"].selected == arelle_revenue
    assert by_concept["Assets"].outcome == RECONCILIATION_COMPANY_FACTS_ONLY
    assert by_concept["Assets"].selected == company_facts_assets


def test_unusable_company_facts_cannot_replace_unusable_arelle() -> None:
    arelle = ReconciliationSourceObservation(
        raw_fact_id=1,
        fact=replace(
            _fact(source="sec_inline_xbrl", value_raw=100),
            value_raw=None,
            value=None,
            quality_flags=(MISSING_VALUE,),
        ),
        arelle_fact_id="fact-revenue",
    )
    company_facts = ReconciliationSourceObservation(
        raw_fact_id=2,
        fact=replace(
            _fact(source="sec_companyfacts", value_raw=100),
            value_raw=None,
            value=None,
            quality_flags=(MISSING_VALUE,),
        ),
    )

    result = reconcile_accession_observations(
        _arelle_result(),
        (arelle, company_facts),
    )

    reconciled = result.observations[0]
    assert reconciled.outcome == RECONCILIATION_COMPANY_FACTS_REPLACEMENT
    assert reconciled.selected is None
    assert reconciled.availability_markers == (
        "arelle_fact_unavailable",
        "company_facts_unusable",
    )


def _fact(*, source: str, value_raw: object) -> NormalizedFact:
    return NormalizedFact(
        cik="0000320193",
        entity_name="Apple Inc.",
        taxonomy="us-gaap",
        concept="Revenue",
        label="Revenue",
        description="Revenue from customers",
        unit="USD",
        value_raw=value_raw,
        value=Decimal(str(value_raw)),
        start_date=date(2024, 9, 29),
        end_date=date(2025, 9, 27),
        period_type="annual",
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 10, 31),
        accession_number=ACCESSION,
        frame="CY2025",
        source=source,
        namespace_uri="https://fasb.org/us-gaap/2025",
        context_id="duration-2025" if source == "sec_inline_xbrl" else None,
        source_document="filing.htm" if source == "sec_inline_xbrl" else None,
        balance="credit" if source == "sec_inline_xbrl" else None,
        is_numeric=True if source == "sec_inline_xbrl" else None,
    )


def _arelle_result(
    *,
    diagnostics: tuple[ArelleDiagnosticRecord, ...] = (),
    concepts: tuple[ArelleConceptRecord, ...] = (),
) -> ArelleFilingResult:
    return ArelleFilingResult(
        schema_version="2",
        adapter_version="1",
        arelle_version="test",
        filing=ArelleFilingIdentity(
            cik="0000320193",
            accession_number=ACCESSION,
            form="10-K",
            filing_date="2025-10-31",
            entry_point_path="filing.htm",
            source_url="https://www.sec.gov/example/filing.htm",
        ),
        status=ARELLE_RESULT_COMPLETE,
        facts=(),
        concepts=concepts,
        contexts=(),
        units=(),
        relationships=(),
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
