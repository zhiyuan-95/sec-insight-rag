import multiprocessing
import os
from pathlib import Path

from src.ingestion import (
    ARELLE_RESULT_COMPLETE,
    ARELLE_RESULT_FAILED,
    ArelleFilingRequest,
    ArelleFilingResult,
    process_arelle_accession,
)


ARELLE_FIXTURE_DIR = Path("data/fixtures/arelle")


def test_process_arelle_accession_returns_serializable_failure_and_stops_worker(
    tmp_path: Path,
) -> None:
    request = ArelleFilingRequest(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        form="10-K",
        filing_date="2025-10-31",
        entry_point_path=str(tmp_path / "missing.htm"),
        source_url="https://www.sec.gov/example/missing.htm",
        content_sha256=None,
    )

    result = process_arelle_accession(request, timeout_seconds=30.0)

    assert result.status == ARELLE_RESULT_FAILED
    assert result.filing.accession_number == request.accession_number
    assert result.worker_pid != os.getpid()
    assert result.session_closed is True
    assert result.facts == ()
    assert result.relationships == ()
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "arelle_worker_failure"
    }
    assert len(result.payload_sha256) == 64
    assert ArelleFilingResult.from_json(result.to_json()) == result
    assert result.worker_pid not in {
        child.pid for child in multiprocessing.active_children()
    }


def test_process_arelle_accession_returns_complete_project_owned_evidence() -> None:
    entry_point = (ARELLE_FIXTURE_DIR / "minimal-instance.xbrl").resolve()
    request = ArelleFilingRequest(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        form="10-K",
        filing_date="2025-10-31",
        entry_point_path=str(entry_point),
        source_url="https://www.sec.gov/example/minimal-instance.xbrl",
        content_sha256=None,
    )

    result = process_arelle_accession(request, timeout_seconds=30.0)

    assert result.status == ARELLE_RESULT_COMPLETE
    assert result.session_closed is True
    assert result.worker_pid != os.getpid()
    assert {fact.display_value for fact in result.facts} == {"100", "70", "30"}
    revenue = next(concept for concept in result.concepts if concept.local_name == "Revenue")
    assert revenue.label == "Revenue"
    assert revenue.documentation == "Revenue from products and services."
    assert {context.context_id for context in result.contexts} == {"duration-2025"}
    context = result.contexts[0]
    assert context.start_date == "2024-09-29"
    assert context.end_date == "2025-09-27"
    assert {unit.unit_id for unit in result.units} == {"usd"}
    assert {relationship.network_kind for relationship in result.relationships} == {
        "calculation",
        "definition",
        "label",
        "presentation",
    }
    assert result.formula_assertions == ()
    assert result.diagnostics
    calculation_diagnostic = next(
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code == "xbrl.5.2.5.2.1:zeroWeight"
    )
    assert len(calculation_diagnostic.relationship_ids) == 1
    affected_relationship = next(
        relationship
        for relationship in result.relationships
        if relationship.evidence_id == calculation_diagnostic.relationship_ids[0]
    )
    assert affected_relationship.network_kind == "calculation"
    fact_diagnostics = [
        diagnostic for diagnostic in result.diagnostics if diagnostic.fact_ids
    ]
    assert len(fact_diagnostics) == 3
    assert result.namespaces
    assert len(result.source_documents) == 4
    assert {document.document_type for document in result.source_documents} == {
        "instance",
        "linkbase",
        "schema",
    }
    assert result.record_counts.facts == 3
    assert ArelleFilingResult.from_json(result.to_json()) == result
    assert result.worker_pid not in {
        child.pid for child in multiprocessing.active_children()
    }
