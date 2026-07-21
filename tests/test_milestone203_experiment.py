from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from experiments.MS200 import milestone203_experiment as experiment
from experiments.MS200 import plan203_arelle_proof as proof_module
from src.analyze.industry_classification import GEMINI_INDUSTRY_ASSIGNMENT_SOURCE
from src.ingestion.filings import FilingMetadata
from src.processing.arelle_mapping_inference import infer_arelle_evidence_mappings
from src.processing.arelle_records import (
    ArelleFilingResult,
    ArelleTimings,
    ConceptEvidence,
    ContextKey,
    ExtractedFact,
    QNameKey,
    RelationshipEdge,
    UnitKey,
)
from src.processing.mapping_targets import CanonicalMetricTarget
from src.storage.company_repository import CompanyRecord, CompanyRepository
from src.storage.concept_mappings_repository import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    ConceptMappingRecord,
    ConceptMappingRepository,
)
from src.storage.database import (
    connect_sqlite,
    connect_sqlite_readonly,
    initialize_database,
)
from src.storage.industry_labels_repository import (
    CompanyIndustryLabelRepository,
    StoredCompanyIndustryLabel,
)


USD = UnitKey((QNameKey("http://www.xbrl.org/2003/iso4217", "USD", "iso4217"),))


def _fact(
    local_name: str,
    *,
    value: str = "100",
    period_type: str = "duration",
    dimensions: tuple = (),
    prefix: str = "custom",
    namespace: str = "https://example.com/issuer/2025",
) -> ExtractedFact:
    return ExtractedFact(
        concept_key=QNameKey(namespace, local_name, prefix),
        context_key=ContextKey(
            context_id="context-1",
            entity_scheme="https://www.sec.gov/CIK",
            entity_identifier="0000789019",
            period_type=period_type,
            start_date="2024-07-01" if period_type == "duration" else None,
            end_date="2025-06-30" if period_type == "duration" else None,
            instant_date="2025-06-30" if period_type == "instant" else None,
            dimensions=dimensions,
        ),
        value=value,
        value_raw=value,
        nil=False,
        unit_key=USD,
        source_document="filing.htm",
        source_line=10,
    )


def _result(
    accession: str,
    form: str,
    facts: tuple[ExtractedFact, ...],
    *,
    labels: dict[str, str] | None = None,
    relationships: tuple[RelationshipEdge, ...] = (),
    status: str = "complete",
) -> ArelleFilingResult:
    label_map = labels or {}
    qnames = tuple(dict.fromkeys(fact.concept_key for fact in facts))
    return ArelleFilingResult(
        accession_number=accession,
        cik="0000789019",
        form=form,
        filing_date="2025-07-30",
        status=status,
        facts=facts,
        concepts=tuple(
            ConceptEvidence(
                concept_key=qname,
                standard_label=label_map.get(qname.local_name, qname.local_name),
                documentation=None,
                type_key=None,
                is_numeric=True,
                numeric_kind="monetary",
                period_type=facts[0].context_key.period_type,
                balance=None,
            )
            for qname in qnames
        ),
        relationships=relationships,
        timings=ArelleTimings(total_seconds=0.25),
    )


def _target(metric: str, statement: str, *aliases: str) -> CanonicalMetricTarget:
    return CanonicalMetricTarget(
        metric_name=metric,
        statement_type=statement,
        aliases=tuple(aliases),
        candidate_concepts=(),
        industry_labels=(),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )


def _session(*results: ArelleFilingResult) -> proof_module.Plan203ProofSession:
    proofs = tuple(
        proof_module.FilingProof(
            requested_form=result.form or "10-K",
            filing=FilingMetadata(
                cik="0000789019",
                accession_number=result.accession_number,
                form=result.form or "10-K",
                filing_date=result.filing_date or "2025-07-30",
                primary_document="filing.htm",
                document_url="https://www.sec.gov/filing.htm",
            ),
            result=result,
        )
        for result in results
    )
    return proof_module.Plan203ProofSession(
        ticker="MSFT",
        cik="0000789019",
        requested_forms=tuple(result.form or "10-K" for result in results),
        registry_path=Path("registry.toml"),
        registry_hash="abc123",
        taxonomy_paths=(),
        companyfacts_count=0,
        proofs=proofs,
        elapsed_seconds=0.5,
        stage_timings=(("sec_acquisition", 0.1),),
    )


def test_readonly_sqlite_requires_existing_file_and_rejects_writes(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        connect_sqlite_readonly(missing)
    assert not missing.exists()

    database = tmp_path / "mapping # test.db"
    with connect_sqlite(database) as connection:
        initialize_database(connection)
        connection.commit()

    with connect_sqlite_readonly(database) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")


def test_equal_specificity_mapping_disagreement_is_excluded() -> None:
    rows = (
        ConceptMappingRecord(
            taxonomy="custom",
            concept="IssuerMetric",
            metric_name="revenue",
            statement_type="income_statement",
            scope_type=MAPPING_SCOPE_COMPANY,
            scope_value="0000789019",
            status=MAPPING_STATUS_APPROVED,
            match_method="human",
            reviewed_by="reviewer",
        ),
        ConceptMappingRecord(
            taxonomy="custom",
            concept="IssuerMetric",
            metric_name="operating_income",
            statement_type="income_statement",
            scope_type=MAPPING_SCOPE_COMPANY,
            scope_value="0000789019",
            status=MAPPING_STATUS_APPROVED,
            match_method="human",
            reviewed_by="reviewer",
        ),
    )

    mappings, _ = experiment._collapse_approved_mappings(
        rows,
        cik="0000789019",
        industry_labels=(),
    )

    assert mappings == {}
    assert experiment._mapping_conflict_selectors(
        rows, cik="0000789019", industry_labels=()
    ) == (("custom", "IssuerMetric"),)


def test_inference_requires_unique_margins_in_both_directions() -> None:
    candidate = _fact("CloudRevenue")
    relationship = RelationshipEdge(
        network_kind="presentation",
        link_role="http://example.com/role/IncomeStatement",
        from_concept=candidate.concept_key,
        to_concept=QNameKey("http://fasb.org/us-gaap/2025", "Revenues", "us-gaap"),
    )
    annual = _result(
        "0000789019-25-000001",
        "10-K",
        (candidate,),
        labels={"CloudRevenue": "Revenue"},
        relationships=(relationship,),
    )
    quarterly_fact = _fact("CloudRevenue")
    quarterly = _result(
        "0000789019-25-000002",
        "10-Q",
        (quarterly_fact,),
        labels={"CloudRevenue": "Revenue"},
        relationships=(relationship,),
    )
    revenue = _target("revenue", "income_statement", "Revenues")
    operating_income = _target(
        "operating_income", "income_statement", "OperatingIncomeLoss"
    )

    rows = infer_arelle_evidence_mappings(
        (annual, quarterly),
        missing_targets=(revenue,),
        applicable_targets=(revenue, operating_income),
    )

    assert rows[0].outcome == "unique_top_candidate"
    assert rows[0].top_candidate_qname == "custom:CloudRevenue"
    assert rows[0].top_candidate_score == sum(
        (
            rows[0].statement_role_score,
            rows[0].presentation_neighborhood_score,
            rows[0].relationship_network_score,
            rows[0].cross_form_recurrence_score,
            rows[0].governed_lexical_score,
        )
    )
    assert rows[0].metric_candidate_margin > 0
    assert rows[0].concept_target_margin > 0


@pytest.mark.parametrize(
    ("statement", "period_type", "expected_outcome"),
    [
        ("balance_sheet", "duration", "no_candidate"),
        ("income_statement", "instant", "no_candidate"),
    ],
)
def test_inference_period_gate_abstains(
    statement: str,
    period_type: str,
    expected_outcome: str,
) -> None:
    result = _result(
        "0000789019-25-000001",
        "10-K",
        (_fact("IssuerMetric", period_type=period_type),),
    )
    target = _target("test_metric", statement, "TestMetric")

    row = infer_arelle_evidence_mappings(
        (result,),
        missing_targets=(target,),
        applicable_targets=(target,),
    )[0]

    assert row.outcome == expected_outcome


def test_statement_role_and_recurrence_without_target_specific_evidence_abstains() -> None:
    payable = _fact("AccountsPayableCurrent", period_type="instant")
    role = RelationshipEdge(
        network_kind="presentation",
        link_role="http://example.com/role/BalanceSheet",
        from_concept=payable.concept_key,
        to_concept=QNameKey("http://fasb.org/us-gaap/2025", "Liabilities", "us-gaap"),
    )
    result = _result(
        "0000789019-25-000001",
        "10-K",
        (payable,),
        relationships=(role,),
    )
    cash = _target(
        "cash_and_equivalents",
        "balance_sheet",
        "CashAndCashEquivalentsAtCarryingValue",
    )

    row = infer_arelle_evidence_mappings(
        (result,),
        missing_targets=(cash,),
        applicable_targets=(cash,),
    )[0]

    assert row.outcome == "no_candidate"
    assert dict(row.rejection_totals)["insufficient_compatibility_evidence"] == 1


def test_full_offline_report_shows_workflow_mapped_missing_and_inference(
    tmp_path: Path,
) -> None:
    assets = _fact(
        "Assets",
        period_type="instant",
        prefix="us-gaap",
        namespace="http://fasb.org/us-gaap/2025",
    )
    annual = _result("0000789019-25-000001", "10-K", (assets,))
    quarterly_assets = _fact(
        "Assets",
        period_type="instant",
        prefix="us-gaap",
        namespace="http://fasb.org/us-gaap/2025",
    )
    quarterly = _result("0000789019-25-000002", "10-Q", (quarterly_assets,))
    database = tmp_path / "experiment.db"
    with connect_sqlite(database) as connection:
        initialize_database(connection)
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(
                cik="0000789019",
                name="Microsoft Corporation",
                ticker="MSFT",
            )
        )
        assert company.company_id is not None
        CompanyIndustryLabelRepository(connection).replace_labels(
            company.company_id,
            (
                StoredCompanyIndustryLabel(
                    company_id=company.company_id,
                    industry_label="Information Technology",
                    assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
                    assignment_reason="Microsoft reports software and cloud services.",
                    confidence=0.94,
                    classifier_version="gemini_item1_business_v1",
                ),
                StoredCompanyIndustryLabel(
                    company_id=company.company_id,
                    industry_label="Consumer Discretionary",
                    assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
                    assignment_reason="Microsoft reports consumer devices and gaming.",
                    confidence=0.94,
                    classifier_version="gemini_item1_business_v1",
                ),
            ),
        )

    report = experiment.build_milestone203_report(
        _session(annual, quarterly),
        database_path=database,
    )

    assert "## 0. Workflow Walkthrough" in report
    assert "## A. Summary" in report
    assert "### B1. Mapped targets" in report
    assert "`total_assets`" in report
    assert "### B2. Missing targets" in report
    assert "Industry bundle: `Consumer Discretionary, Information Technology`" in report
    assert "Industry-label source: `gemini_item1_business_classification`" in report
    assert "`advertising_expense`" in report
    assert "## C. Arelle-evidence inference" in report
    assert "Formula suggestions and all LLM calls are intentionally not run" in report
    assert "Count integrity: `Y`" in report


def test_proof_cli_delegates_once_and_preserves_failed_only_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failed_session = proof_module.Plan203ProofSession(
        ticker="MSFT",
        cik="0000789019",
        requested_forms=("10-K",),
        registry_path=tmp_path / "registry.toml",
        registry_hash="abc",
        taxonomy_paths=(),
        companyfacts_count=0,
        proofs=(
            proof_module.FilingProof(
                requested_form="10-K",
                failure_stage="filing_package",
                failure_reason="offline verification failed",
            ),
        ),
        elapsed_seconds=0.1,
        stage_timings=(),
    )
    calls = []
    monkeypatch.setattr(
        proof_module,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "ticker": "MSFT",
                "env_file": "config.env",
                "forms": ["10-K"],
                "registry": Path("registry.toml"),
                "taxonomy_dir": Path("taxonomy"),
                "filings_dir": None,
                "cache_dir": Path("cache"),
                "report": tmp_path / "report.md",
                "sync_taxonomies": False,
            },
        )(),
    )
    monkeypatch.setattr(
        proof_module,
        "run_plan203_proof",
        lambda **kwargs: calls.append(kwargs) or failed_session,
    )
    monkeypatch.setattr(proof_module, "_write_report", lambda *args, **kwargs: None)

    assert proof_module.main() == 1
    assert len(calls) == 1


def test_atomic_report_failure_preserves_previous_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(experiment.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("busy")))

    with pytest.raises(OSError, match="busy"):
        experiment._atomic_write(report_path, "new")

    assert report_path.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_readonly_repository_can_load_approved_mapping(tmp_path: Path) -> None:
    database = tmp_path / "approved.db"
    with connect_sqlite(database) as connection:
        repository = ConceptMappingRepository(connection)
        repository.initialize()
        repository.upsert_mappings(
            (
                ConceptMappingRecord(
                    taxonomy="custom",
                    concept="IssuerRevenue",
                    metric_name="revenue",
                    statement_type="income_statement",
                    scope_type=MAPPING_SCOPE_COMPANY,
                    scope_value="0000789019",
                    status=MAPPING_STATUS_APPROVED,
                    match_method="human_review",
                    reviewed_by="reviewer",
                ),
            )
        )

    rows, conflicts, status = experiment._load_approved_mapping_rows(
        database,
        cik="0000789019",
        industry_labels=(),
    )

    assert len(rows) == 1
    assert conflicts == ()
    assert status == "available; 1 applicable approved rows"


def test_only_persisted_gemini_labels_are_used_for_ms203(tmp_path: Path) -> None:
    database = tmp_path / "labels.db"
    with connect_sqlite(database) as connection:
        initialize_database(connection)
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(
                cik="0000789019",
                name="Microsoft Corporation",
                ticker="MSFT",
            )
        )
        assert company.company_id is not None
        CompanyIndustryLabelRepository(connection).replace_labels(
            company.company_id,
            (
                StoredCompanyIndustryLabel(
                    company_id=company.company_id,
                    industry_label="Information Technology",
                    assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
                    assignment_reason="Gemini classification",
                    confidence=0.91,
                ),
                StoredCompanyIndustryLabel(
                    company_id=company.company_id,
                    industry_label="Communication Services",
                    assignment_source="manual_source_controlled_registry",
                    assignment_reason="Legacy fallback",
                ),
            ),
        )

    assignment, status = experiment._load_persisted_gemini_industry_assignment(
        database,
        ticker="MSFT",
        cik="0000789019",
    )

    assert assignment.assigned_industry_labels == ("Information Technology",)
    assert assignment.assignment_source == GEMINI_INDUSTRY_ASSIGNMENT_SOURCE
    assert status == "available; 1 approved Gemini labels"


def test_missing_persisted_gemini_labels_use_common_only_without_registry_fallback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "labels.db"
    with connect_sqlite(database) as connection:
        initialize_database(connection)
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(
                cik="0000789019",
                name="Microsoft Corporation",
                ticker="MSFT",
            )
        )
        assert company.company_id is not None
        CompanyIndustryLabelRepository(connection).replace_labels(
            company.company_id,
            (
                StoredCompanyIndustryLabel(
                    company_id=company.company_id,
                    industry_label="Information Technology",
                    assignment_source="manual_source_controlled_registry",
                    assignment_reason="Legacy fallback",
                ),
            ),
        )

    assignment, status = experiment._load_persisted_gemini_industry_assignment(
        database,
        ticker="MSFT",
        cik="0000789019",
    )

    assert assignment.assigned_industry_labels == ()
    assert assignment.label_status == "needs_label_review"
    assert assignment.assignment_source == "persisted_gemini_labels_unavailable"
    assert status == (
        "no_approved_gemini_labels; 1 non-Gemini approved rows ignored; common-only"
    )


def test_missing_mapping_table_is_reported_without_initializing_it(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.db"
    sqlite3.connect(database).close()

    assignment, label_status = experiment._load_persisted_gemini_industry_assignment(
        database,
        ticker="MSFT",
        cik="0000789019",
    )

    rows, conflicts, status = experiment._load_approved_mapping_rows(
        database,
        cik="0000789019",
        industry_labels=(),
    )

    assert rows == ()
    assert conflicts == ()
    assert status == "table_missing_read_only; source-controlled mappings only"
    assert assignment.assigned_industry_labels == ()
    assert label_status == "table_missing_read_only; common-only"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall() == []
