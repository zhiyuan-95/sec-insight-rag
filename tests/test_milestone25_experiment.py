import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

from src.config import Settings
from src.ingestion import FilingMetadata
from src.processing import NormalizedFact
from src.processing.formula_proposals import (
    FormulaProposalComponentResponse,
    FormulaProposalProviderResult,
)
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    ConceptMappingRecord,
    ConceptMappingRepository,
    FilingRecord,
    FilingRepository,
    FinancialMetric,
    FinancialMetricRepository,
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    RawFactRepository,
    connect_sqlite,
)


def _load_experiment_module() -> ModuleType:
    module_path = Path("experiments/MS2_5/milestone25_live_sec_inspection.py")
    spec = importlib.util.spec_from_file_location("milestone25_live_sec_inspection", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_milestone25_experiment_presents_first_time_ingestion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    assert output == ""
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "Company in system" in report
    assert "Update check needed this session" in report
    assert "SEC update check performed" in report
    assert "local data reused; no SEC request made" in report
    assert "New filings ingested this session" in report
    assert "none" in report
    assert (tmp_path / "experiment.db").exists()
    assert (tmp_path / "exports" / "companies.csv").exists()
    assert (tmp_path / "exports" / "financial_metrics.csv").exists()


def test_milestone25_experiment_reports_missing_sec_user_agent(
    tmp_path: Path,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert output == ""
    assert "Execution Warning" in report
    assert "SEC_USER_AGENT is required for live SEC experiment runs" in report


def test_milestone25_uses_ticker_specific_default_report_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    monkeypatch.setattr(experiment, "EXPERIMENT_DIR", tmp_path)
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "msft",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report_path = tmp_path / "milestone25_mapping_report_MSFT.md"
    report = report_path.read_text(encoding="utf-8")

    assert exit_code == 1
    assert output == ""
    assert report_path.exists()
    assert "SEC_USER_AGENT is required for live SEC experiment runs" in report


def test_milestone25_write_report_flag_preserves_markdown_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--write-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "saved Plan 2.5 target mapping report" in report
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "Evidence Locations" not in report
    assert "Financial Metric Data Lineage View" not in report
    assert "Annual XBRL Financial Metrics" not in report
    assert "Phase 2" not in report


def test_milestone25_saves_warning_when_csv_export_is_locked(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    original_export_query = experiment._export_query

    def locked_export(connection, query: str, path: Path) -> None:
        if path.name == "financial_metrics.csv":
            raise PermissionError("locked by another process")
        original_export_query(connection, query, path)

    monkeypatch.setattr(experiment, "_export_query", locked_export)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "CSV export skipped for financial_metrics" in report
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report


def test_milestone25_full_report_flag_prints_detailed_markdown(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "--full-report kept for CLI compatibility" in report
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "Financial Metric Data Lineage View" not in report
    assert "Annual XBRL Financial Metrics" not in report


def test_milestone25_markdown_table_keeps_identifier_lists_as_text() -> None:
    experiment = _load_experiment_module()
    raw_fact_ids = ",".join(str(100000000000000000000000000000 + index) for index in range(3))
    context_hash = "1234567890123456789012345678901234567890"

    lines = experiment._markdown_table(
        [
            {
                "matched_raw_fact_ids": raw_fact_ids,
                "formula_context_hash": context_hash,
                "amount": "123456789",
            }
        ]
    )
    table = "\n".join(lines)

    assert raw_fact_ids in table
    assert context_hash in table
    assert "123.46M" in table
    assert experiment._format_presentation_number("9" * 80) == "9" * 80


def test_milestone25_report_shows_approved_learned_mapping_reuse(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(
        experiment,
        "ingest_company",
        _fake_ingest_company_with_mapping_evidence(calls),
    )
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "Target Metrics Mapping Status" in report
    assert "Target XBRL concepts checked" in report
    target_status_section = report.split("Target Metrics Mapping Status", 1)[1].split(
        "Proposed Formulas For Formula Recommendations",
        1,
    )[0]
    target_status_header = next(
        line for line in target_status_section.splitlines() if line.startswith("| ")
    )
    assert [cell.strip() for cell in target_status_header.strip("|").split("|")] == [
        "Metric type",
        "Metric",
        "Statement",
        "Mapping status",
        "Mapped target concepts",
        "Coverage detail",
        "Approved alternates",
        "Target XBRL concepts checked",
    ]
    assert "required_for_core" not in target_status_section
    assert "unit_count" not in target_status_section
    assert "target_candidate_xbrl_concept" not in report
    assert "target_xbrl_concept_candidate" not in report
    assert "Mapping Candidates (Review Required):" not in report
    assert "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" in report
    assert "## Human Question" not in report
    assert "Company Industry Labels:" not in report
    assert "Unknown SEC/XBRL Concepts Not Mapped To Base Metrics:" not in report
    snapshot = experiment._snapshot(tmp_path / "experiment.db", "TEST")
    unknown_coverage = next(
        row
        for row in snapshot["raw_fact_mapping_coverage"]
        if row["coverage_item"] == "distinct unknown raw concepts"
    )
    review_pool = next(
        row
        for row in snapshot["mapping_profile_reuse"]
        if row["evidence_item"] == "mapping expansion review pool"
    )
    assert review_pool["value"] == unknown_coverage["count"]


def test_milestone25_report_shows_report_only_debt_recovery_diagnostics(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company_with_debt_components(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "Debt Recovery Formula Catalog:" not in report
    assert "Debt Recovery Diagnostics Summary:" not in report
    snapshot = experiment._snapshot(tmp_path / "experiment.db", "TEST")
    current = next(
        row
        for row in snapshot["debt_recovery_diagnostics"]
        if row["target_metric_name"] == "debt_current"
    )
    assert current["target_recovery_status"] == "derived_from_components"
    assert current["formula_name"] == "debt_current_components"
    assert current["calculated_value"] == "50"
    assert "current_finance_lease_debt" in current["assumed_zero_components"]
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name = 'debt_current'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0


def test_milestone25_report_shows_report_only_formula_proposals_from_found_targets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        assert formula_context["target_primary_statement"] == target.statement_type
        assert formula_context["period_context"]["fiscal_year"] == 2025
        component_row = next(
            (row for row in fact_pool if "found_target" in row["mapping_statuses"]),
            fact_pool[0],
        )
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="proposed",
            no_formula=False,
            target_is_zero=False,
            formula_expression=f"{target.target_metric_name} = {component_row['taxonomy']}:{component_row['concept']}",
            components=(
                FormulaProposalComponentResponse(
                    component_name="context component",
                    taxonomy=str(component_row["taxonomy"]),
                    concept=str(component_row["concept"]),
                    operator="+",
                    role="already found target fact reused as component evidence",
                    reason="The component is in the eligible same-period raw fact pool",
                ),
            ),
            confidence=0.8,
            reason="test proposal",
            uncertainty="review required",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposals",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")
    snapshot = experiment._snapshot(tmp_path / "experiment.db", "TEST")

    assert exit_code == 0
    assert output == ""
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "LLM Formula Proposal Diagnostics Summary" in report
    assert "LLM Formula Proposal Diagnostics" in report
    assert "LLM Formula Proposal Component Evidence" in report
    assert "Eligible Formula Proposal Raw Fact Pool" in report
    assert "formula proposal model panel" in report
    assert "found_target" in report
    assert "validated_component_pool" in report
    assert "period-scoped formula contexts" in report
    assert "cap_per_target" in report
    assert "generated_new" in report
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name <> 'revenue'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0
    assert snapshot["formula_proposal_summary"][0]["value"] == "not_run"


def test_milestone25_report_shows_report_only_zero_target_proposals(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        component_row = fact_pool[0]
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="target_zero",
            no_formula=False,
            target_is_zero=True,
            formula_expression=f"{target.target_metric_name} = 0",
            components=(
                FormulaProposalComponentResponse(
                    component_name="zero evidence",
                    taxonomy=str(component_row["taxonomy"]),
                    concept=str(component_row["concept"]),
                    operator="+",
                    role="same-period raw fact evidence for zero-target review",
                    reason="The evidence fact is in the eligible same-period raw fact pool.",
                ),
            ),
            confidence=0.6,
            reason="Target may be zero based on supplied same-period evidence.",
            uncertainty="Requires review before treating the missing target as zero.",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposals",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert "target_zero" in report
    assert "target_is_zero" in report
    assert "validated_zero_evidence_pool" in report
    assert "zero-target proposal rows" in report
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name <> 'revenue'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0


def test_milestone25_formula_proposals_reuse_failed_provider_result_within_run(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    original_build_contexts = experiment.build_formula_proposal_contexts

    def duplicate_contexts(*, target, fact_pool):
        contexts = original_build_contexts(target=target, fact_pool=fact_pool)
        return contexts[:1] + contexts[:1]

    provider_calls: list[str] = []

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        provider_calls.append(str(formula_context["formula_context_hash"]))
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="provider_failed",
            no_formula=True,
            target_is_zero=False,
            formula_expression="",
            components=(),
            confidence=0.0,
            reason="",
            uncertainty="",
            error="test provider failure",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "build_formula_proposal_contexts", duplicate_contexts)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposals",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert output == ""
    assert len(provider_calls) == 1
    assert "provider_failed" in report
    assert "test provider failure" in report


def test_milestone25_report_presents_new_filings_when_sec_update_ingests_them(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company_with_update(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    assert output == ""
    assert "Company in system" in report
    assert "Update check needed this session" in report
    assert "SEC update check performed" in report
    assert "SEC checked; new active-window filing data ingested" in report
    assert "New filings ingested this session" in report
    assert "10-Q test-10q-new" in report
    assert "10-Q check due" in report
    assert "next check date before session: 2020-01-01" in report


def _fake_ingest_company(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filing_repository.upsert_filings(
                company.company_id,
                [
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10k",
                        form_type="10-K",
                        filing_date=date(2025, 2, 15),
                        fiscal_year=2025,
                        fiscal_period="FY",
                        local_path=settings.stock_filings_base_dir / "test-10k.htm",
                    ),
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q",
                        form_type="10-Q",
                        filing_date=date(2025, 5, 15),
                        fiscal_year=2025,
                        fiscal_period="Q1",
                        local_path=settings.stock_filings_base_dir / "test-10q.htm",
                    ),
                ],
            )
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "reused_local",
            sec_checked=call_number == 1,
            refresh_due_10k=False,
            refresh_due_10q=False,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10k",
                    form="10-K",
                    filing_date="2025-02-15",
                    primary_document="test-10k.htm",
                    document_url="https://example.test/test-10k.htm",
                ),
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q",
                    form="10-Q",
                    filing_date="2025-05-15",
                    primary_document="test-10q.htm",
                    document_url="https://example.test/test-10q.htm",
                ),
            ),
        )

    return ingest


def _fake_ingest_company_with_mapping_evidence(calls: list[str]):
    base_ingest = _fake_ingest_company(calls)

    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        result = base_ingest(ticker, settings)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            raw_repository.initialize()
            raw_repository.upsert_facts(
                [
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        taxonomy="custom",
                        concept="CustomerRevenueApproved",
                        label="Customer revenue approved",
                    ),
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        concept="CustomUnmappedDisclosure",
                        label="Custom unmapped disclosure",
                    )
                ]
            )
            repository = ConceptMappingRepository(connection)
            repository.initialize()
            repository.upsert_mappings(
                (
                    ConceptMappingRecord(
                        taxonomy="custom",
                        concept="CustomerRevenueApproved",
                        metric_name="revenue",
                        statement_type="income_statement",
                        scope_type=MAPPING_SCOPE_COMPANY,
                        scope_value="0000000001",
                        status=MAPPING_STATUS_APPROVED,
                        confidence=0.99,
                        match_method="manual_review",
                        evidence={"reason": "approved company concept profile test"},
                        reviewed_by="tester",
                        reviewed_at="2026-01-01T00:00:00+00:00",
                    ),
                )
            )
        return result

    return ingest


def _fake_ingest_company_with_debt_components(calls: list[str]):
    base_ingest = _fake_ingest_company(calls)

    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        result = base_ingest(ticker, settings)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            company = company_repository.get_by_ticker(ticker)
            assert company is not None
            assert company.company_id is not None
            raw_repository.upsert_facts(
                [
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        concept="LongTermDebtCurrent",
                        label="Long-term debt current",
                    )
                ]
            )
            raw_fact_by_concept = {
                record.fact.concept: record.raw_fact_id
                for record in raw_repository.list_fact_records("0000000001")
            }
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact_by_concept["LongTermDebtCurrent"],
                        statement_type="balance_sheet",
                        metric_name="long_term_debt_current",
                        value_numeric=Decimal("50"),
                        value_raw=50,
                        unit="USD",
                        period_type="instant",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        end_date=date(2025, 12, 31),
                        filing_date=date(2026, 2, 1),
                    )
                ]
            )
        return result

    return ingest


def _fake_ingest_company_with_update(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 8, 15) if call_number == 2 else date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1) if call_number == 2 else date(2020, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filings = [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10k",
                    form_type="10-K",
                    filing_date=date(2025, 2, 15),
                    fiscal_year=2025,
                    fiscal_period="FY",
                    local_path=settings.stock_filings_base_dir / "test-10k.htm",
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10q",
                    form_type="10-Q",
                    filing_date=date(2025, 5, 15),
                    fiscal_year=2025,
                    fiscal_period="Q1",
                    local_path=settings.stock_filings_base_dir / "test-10q.htm",
                ),
            ]
            if call_number == 2:
                filings.append(
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q-new",
                        form_type="10-Q",
                        filing_date=date(2025, 8, 15),
                        fiscal_year=2025,
                        fiscal_period="Q2",
                        local_path=settings.stock_filings_base_dir / "test-10q-new.htm",
                    )
                )
            filing_repository.upsert_filings(company.company_id, filings)
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "updated",
            sec_checked=True,
            refresh_due_10k=False,
            refresh_due_10q=call_number == 2,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q-new" if call_number == 2 else "test-10q",
                    form="10-Q",
                    filing_date="2025-08-15" if call_number == 2 else "2025-05-15",
                    primary_document="test-10q-new.htm" if call_number == 2 else "test-10q.htm",
                    document_url="https://example.test/test-10q-new.htm",
                ),
            ),
        )

    return ingest


def _fact(
    *,
    form: str,
    accession_number: str,
    taxonomy: str = "us-gaap",
    concept: str = "Revenues",
    label: str = "Revenues",
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Test Company",
        taxonomy=taxonomy,
        concept=concept,
        label=label,
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form=form,
        filed_date=date(2025, 2, 15),
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )


def _env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        f"SEC_USER_AGENT=Test contact@example.com\nKNOWLEDGE_STORAGE_DIR={tmp_path / 'knowledge'}\n",
        encoding="utf-8",
    )
    return env_file
