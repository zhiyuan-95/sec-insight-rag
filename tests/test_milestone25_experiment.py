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
    initialize_database,
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


def _report_section(report: str, start: str, end: str | None = None) -> str:
    section = report.split(start, 1)[1]
    if end is not None:
        section = section.split(end, 1)[0]
    return section


def _assert_formula_progress_output(output: str) -> None:
    assert "[formula proposals]" in output
    assert "missing target(s) found" in output
    assert "Missing targets selected:" in output
    assert "Handling missing target 1/1:" in output
    assert "Context 1/" in output
    assert "Formula proposal generation complete:" in output
    assert "reused cached recommendation" not in output
    assert "reused identical context from this run" not in output


def test_milestone25_formula_rows_collapse_same_recommended_components() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "debt_current = LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.90",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "debt_current = LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.90",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-Q periods: 2021 Q1 - 2025 Q4 / instant / USD / 10-Q",
                "forms": "10-Q",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
        ],
    }

    formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )
    quarterly_formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-Q",
    )
    assert formula_rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": "2024-2025",
            "Providers": "gemini (gemini-2.5-flash); openai (gpt-4.1-mini)",
            "Formula": "debt_current = LongTermDebtCurrent",
            "Validation status": "validated_component_pool",
            "Confidence": "0.80; 0.90",
            "Reason": "same component evidence",
        }
    ]
    assert quarterly_formula_rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": (
                "2021 q1 - 2021 q3, 2022 q1 - 2022 q3, 2023 q1 - 2023 q3, "
                "2024 q1 - 2024 q3, 2025 q1 - 2025 q3"
            ),
            "Providers": "gemini (gemini-2.5-flash)",
            "Formula": "debt_current = LongTermDebtCurrent",
            "Validation status": "validated_component_pool",
            "Confidence": "0.80",
            "Reason": "same component evidence",
        }
    ]
    assert "Recommendation" not in formula_rows[0]
    assert "Target concept" not in formula_rows[0]
    assert "Components" not in formula_rows[0]
    assert "Components" not in quarterly_formula_rows[0]
    assert "/" not in formula_rows[0]["Period context"]
    assert "/" not in quarterly_formula_rows[0]["Period context"]
    assert "q4" not in quarterly_formula_rows[0]["Period context"]


def test_milestone25_formula_rows_do_not_overlap_when_provider_periods_disagree() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:CommercialPaper",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "commercial paper evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:OtherLiabilitiesCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.70",
                "reason": "other liabilities evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:CommercialPaper",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "commercial paper evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2022 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2022 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
        ],
    }

    formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )
    assert [row["Period context"] for row in formula_rows] == [
        "2024-2025",
        "2025",
        "2024",
        "2022-2023",
    ]
    assert "2021-2024" not in [row["Period context"] for row in formula_rows]
    assert formula_rows[0]["Providers"] == "gemini (gemini-2.5-flash)"
    assert formula_rows[0]["Formula"] == "debt_current = LongTermDebtCurrent + CommercialPaper"
    assert formula_rows[1]["Providers"] == "openai (gpt-4.1-mini)"
    assert formula_rows[1]["Formula"] == "debt_current = LongTermDebtCurrent + OtherLiabilitiesCurrent"
    assert formula_rows[2]["Providers"] == "openai (gpt-4.1-mini)"
    assert formula_rows[2]["Formula"] == "debt_current = LongTermDebtCurrent"
    assert formula_rows[3]["Formula"] == "debt_current = LongTermDebtCurrent"
    assert formula_rows[3]["Providers"] == "gemini (gemini-2.5-flash); openai (gpt-4.1-mini)"
    assert all("Components" not in row for row in formula_rows)


def test_milestone25_xbrl_concepts_provided_counts_by_period() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-shared",
                "period_context": "10-K periods: 2024 FY, 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-shared",
                "period_context": "10-K periods: 2024 FY, 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-2023",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "concepts_provided": "us-gaap:LongTermDebtCurrent",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "quarterly-shared",
                "period_context": "10-Q periods: 2025 Q1 - 2025 Q2 / instant / USD / 10-Q",
                "forms": "10-Q",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
        ],
    }

    assert experiment._xbrl_concepts_provided_10k_rows(snapshot) == [
        {"Year": "2023", "# of concepts provided": 1},
        {"Year": "2024", "# of concepts provided": 2},
        {"Year": "2025", "# of concepts provided": 2},
    ]
    assert experiment._xbrl_concepts_provided_10q_rows(snapshot) == [
        {"Year": "2025", "Q1": 2, "Q2": 2, "Q3": ""},
    ]


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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "Company in system" in report
=======
    assert "## 0. Compact Summary" in report
    assert "## 0A. XBRL Concepts Provided By Period" in report
    assert "### # of concepts provided from XBRL - 10-K" in report
    assert "### # of concepts provided from XBRL - 10-Q" in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Semantic Candidates For Missing Targets" not in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
    assert "## 4. Selected Concept Pools For Formula Recommendations" not in report
    assert "## 4. Final Recommendations For Missing Targets" not in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "### 10-K" in report
    assert "### 10-Q" in report
    assert "Company in system" in report
    assert "Setup ingestion duration seconds" in report
    assert "Unchanged-company reuse duration seconds" in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
    assert "Update check needed this session" in report
    assert "SEC update check performed" in report
    assert "local data reused; no SEC request made" in report
    assert "New filings ingested this session" in report
<<<<<<< HEAD
    assert "none" in report
=======
    assert "Metric-First Coverage Resolution" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
            "--no-formula-proposals",
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


def test_milestone25_error_report_preserves_local_company_snapshot(
    tmp_path: Path,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    database_path = tmp_path / "experiment.db"
    with connect_sqlite(database_path) as connection:
        initialize_database(connection)
        CompanyRepository(connection).upsert_company(
            CompanyRecord(cik="0000789019", name="Microsoft Corp.", ticker="TEST")
        )
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(database_path),
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

    company_line = next(line for line in report.splitlines() if "Company in system" in line)
    sec_result_line = next(line for line in report.splitlines() if "SEC result" in line)
    assert exit_code == 1
    assert output == ""
    assert "yes" in company_line
    assert "experiment_error" in sec_result_line
    assert "company is not in local storage" not in report
    assert "0000789019" in report
    assert "789.02K" not in report


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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "Evidence Locations" not in report
    assert "Financial Metric Data Lineage View" not in report
    assert "Annual XBRL Financial Metrics" not in report
=======
    assert "## 0. Compact Summary" in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
    assert "Component Evidence Samples" not in report
    assert "Evidence Locations" not in report
    assert "Appendix A: Target-Level XBRL Concept Coverage" not in report
    assert "Provider-Level Formula Diagnostics" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report
=======
    assert "## 0. Compact Summary" in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "Evidence Boundary" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)


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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "--full-report kept for CLI compatibility" in report
    assert "Target Metrics Mapping Status" in report
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "Financial Metric Data Lineage View" not in report
    assert "Annual XBRL Financial Metrics" not in report
=======
    assert "## 0. Compact Summary" in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
    assert "--full-report kept for CLI compatibility" in report
    assert "Appendix A: Target-Level XBRL Concept Coverage" not in report
    assert "Provider-Level Formula Diagnostics" not in report
    assert "Raw Fact and Unknown Concept Evidence" not in report
    assert "Financial Metric Data Lineage View" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)


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
    year_table = "\n".join(experiment._markdown_table([{"Year": "2026", "Q1": 223}]))
    assert "2026" in year_table
    assert "2.03K" not in year_table
    assert experiment._format_presentation_number("9" * 80) == "9" * 80


<<<<<<< HEAD
def test_milestone25_formula_rows_include_validation_reason() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "target_raw_fact_coverage": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "status": experiment.STATUS_MISSING_TARGET,
                "target_xbrl_concept": "us-gaap:DebtCurrent",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "2026 Q3 | instant | USD | ->2026-03-31 | 10-Q | test-accession",
                "provider_status": "proposed",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "formula_expression": "debt_current = us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "validation_skip_reason": "formula_components_duplicate_same_period_facts",
                "confidence": "0.95",
                "reason": "test proposal",
            }
        ],
    }

    rows = experiment._proposed_formula_rows_for_missing_targets(snapshot, form_type="10-Q")

    assert rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": "2026 q3",
            "Providers": "gemini (gemini-2.5-flash)",
            "Formula": "debt_current = LongTermDebtCurrent",
            "Validation status": "validation_failed",
            "Validation reason": "formula_components_duplicate_same_period_facts",
            "Confidence": "0.95",
            "Reason": "test proposal",
        }
    ]


def test_milestone25_xbrl_concepts_provided_by_period_counts_raw_facts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    base_ingest = _fake_ingest_company(calls)

    def ingest_with_extra_raw_facts(ticker: str, settings: Settings) -> SimpleNamespace:
        result = base_ingest(ticker, settings)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            raw_repository.initialize()
            raw_repository.upsert_facts(
                [
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        concept="Assets",
                        label="Assets",
                        fiscal_period="FY",
                    ),
                    _fact(
                        form="10-K/A",
                        accession_number="test-10ka",
                        concept="Liabilities",
                        label="Liabilities",
                        fiscal_period="FY",
                    ),
                    _fact(
                        form="10-Q",
                        accession_number="test-10q",
                        concept="Assets",
                        label="Assets",
                        fiscal_period="Q1",
                    ),
                    _fact(
                        form="10-Q",
                        accession_number="test-10q",
                        concept="Liabilities",
                        label="Liabilities",
                        fiscal_period="Q1",
                    ),
                    _fact(
                        form="10-Q/A",
                        accession_number="test-10qa",
                        concept="StockholdersEquity",
                        label="Stockholders' equity",
                        fiscal_period="Q2",
                    ),
                ]
            )
        return result

    monkeypatch.setattr(experiment, "ingest_company", ingest_with_extra_raw_facts)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
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

    annual_section = report.split("### # of concepts provided from XBRL - 10-K", 1)[1].split(
        "### # of concepts provided from XBRL - 10-Q",
        1,
    )[0]
    annual_row = next(line for line in annual_section.splitlines() if line.startswith("| 2025"))
    annual_cells = [cell.strip() for cell in annual_row.strip("|").split("|")]
    quarterly_section = report.split("### # of concepts provided from XBRL - 10-Q", 1)[1].split(
        "Boundary:",
        1,
    )[0]
    quarterly_row = next(line for line in quarterly_section.splitlines() if line.startswith("| 2025"))
    quarterly_cells = [cell.strip() for cell in quarterly_row.strip("|").split("|")]

    assert exit_code == 0
    assert output == ""
    assert annual_cells == ["2025", "3"]
    assert quarterly_cells == ["2025", "2", "1", ""]


def test_milestone25_report_shows_approved_learned_mapping_reuse(
=======
def test_milestone25_markdown_table_keeps_period_context_as_label() -> None:
    experiment = _load_experiment_module()

    lines = experiment._markdown_table(
        [
            {
                "Metric": "debt_current",
                "Period context": "2025",
                "Period coverage": "active 10-K periods: 2021 FY - 2025 FY",
                "amount": "2025",
            }
        ]
    )
    table = "\n".join(lines)
    cells = [cell.strip() for cell in lines[2].strip("|").split("|")]

    assert "2.03K" in table
    assert cells == [
        "debt_current",
        "2025",
        "active 10-K periods: 2021 FY - 2025 FY",
        "2.03K",
    ]


def test_milestone25_formula_proposal_targets_collapse_missing_tags_by_metric() -> None:
    experiment = _load_experiment_module()

    targets = experiment._formula_proposal_targets(
        [
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "depreciation_and_amortization",
                "statement_type": "cash_flow_statement",
                "target_xbrl_concept": "us-gaap:DepreciationAndAmortization",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DepreciationAndAmortization",
                "industry_label": "Common Base",
            },
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "depreciation_and_amortization",
                "statement_type": "cash_flow_statement",
                "target_xbrl_concept": "us-gaap:DepreciationDepletionAndAmortization",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DepreciationDepletionAndAmortization",
                "industry_label": "Common Base",
            },
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DebtCurrent",
                "industry_label": "Common Base",
            },
        ],
        target_limit=None,
    )

    assert [target.target_metric_name for target in targets] == [
        "depreciation_and_amortization",
        "debt_current",
    ]
    assert "DepreciationAndAmortization" in targets[0].notes
    assert "DepreciationDepletionAndAmortization" in targets[0].notes


<<<<<<< HEAD
def test_milestone25_report_shows_profile_reuse_and_candidate_level_semantic_evidence(
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
            "--no-formula-proposals",
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
<<<<<<< HEAD
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
=======
    assert "Approved Company Concept Profile Reuse And Semantic Discovery" not in report
    assert "semantic discovery status" not in report
    assert "Metric-First Coverage Resolution" not in report
    assert "Appendix A: Target-Level XBRL Concept Coverage" not in report
    target_coverage_section = _report_section(
        report,
        "## 1. Target Metrics Mapping Status",
        "## 2. Semantic Candidates For Missing Targets",
    )
    target_coverage_header = next(
        line for line in target_coverage_section.splitlines() if line.startswith("| ")
    )
    assert [cell.strip() for cell in target_coverage_header.strip("|").split("|")] == [
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
        "Metric type",
        "Metric",
        "Statement",
        "Mapping status",
        "Mapped target concepts",
        "Coverage detail",
        "Approved alternates",
        "Target XBRL concepts checked",
    ]
<<<<<<< HEAD
    assert "required_for_core" not in target_status_section
    assert "unit_count" not in target_status_section
    assert "target_candidate_xbrl_concept" not in report
    assert "target_xbrl_concept_candidate" not in report
    assert "Mapping Candidates (Review Required):" not in report
    assert "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" in report
    assert "## Human Question" not in report
    assert "Company Industry Labels:" not in report
    assert "Unknown SEC/XBRL Concepts Not Mapped To Base Metrics:" not in report
=======
    assert "Missing or unapproved target concepts" not in target_coverage_header
    assert "common base" in target_coverage_section
    assert "required_for_core" not in target_coverage_section
    assert "unit_count" not in target_coverage_section
    semantic_section = _report_section(
        report,
        "## 2. Semantic Candidates For Missing Targets",
        "## 3. Proposed Formulas For Formula Recommendations",
    )
    assert "### 10-K" in semantic_section
    assert "### 10-Q" in semantic_section
    assert "Target concept" not in semantic_section
    assert "Recommended concepts by semantic similarity" in semantic_section
    assert "Period coverage" in semantic_section
    assert "Requires review" not in semantic_section
    assert "Target candidate" not in semantic_section
    assert "target_xbrl_concept_candidate" not in report
    assert "CustomerAccountsReceivable" in semantic_section
    assert "AccountsReceivableNetCurrent" not in semantic_section
    assert "active 10-K periods: 2025 FY" in semantic_section
    assert "active 10-Q periods: 2025 Q1" in semantic_section
    assert "custom:" not in report
    assert "us-gaap:" not in report
    assert "custom:CustomerRevenueGross" not in semantic_section
    assert "## Human Question" not in report
    assert "### Company Industry Labels" not in report
    assert report.count("## 1. Target Metrics Mapping Status") == 1
    assert report.count("## 2. Semantic Candidates For Missing Targets") == 1
    assert "Unknown Concept Review Pool" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
    revenue_resolution = next(
        row
        for row in snapshot["metric_coverage_resolution"]
        if row["internal_metric_name"] == "revenue"
    )
    assert review_pool["value"] == unknown_coverage["count"]
    assert revenue_resolution["coverage_status"] == "mapped"
    assert revenue_resolution["reviewer_action"] == "none"


=======
>>>>>>> 22949cb (Remove obsolete milestone 2.5 artifacts)
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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "Debt Recovery Formula Catalog:" not in report
    assert "Debt Recovery Diagnostics Summary:" not in report
=======
    assert "Debt Recovery Formula Catalog" not in report
    assert "Report-Only Debt Recovery Diagnostics" not in report
    assert "Debt Recovery Diagnostic Rows" not in report
    assert "Debt Recovery Component Evidence" not in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
<<<<<<< HEAD
    assert output == ""
    assert "XBRL Concepts Provided By Period" in report
    assert "Proposed Formulas For Formula Recommendations" in report
    assert "LLM Formula Proposal Diagnostics Summary" not in report
    assert "LLM Formula Proposal Diagnostics" not in report
    assert "LLM Formula Proposal Component Evidence" not in report
    assert "Eligible Formula Proposal Raw Fact Pool" not in report
    assert "accounts_receivable = Revenues" in report
    assert "validated_component_pool" in report
    assert "fake_provider (fake_model)" in report
=======
    _assert_formula_progress_output(output)
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
    assert "## 4. Selected Concept Pools For Formula Recommendations" not in report
    assert "Formula / Zero Diagnostics Summary" not in report
    assert "Formula Proposal Run Summary" not in report
    assert "Provider-Level Formula Diagnostics" not in report
    assert "Eligible Formula Proposal Raw Fact Pool" not in report
    formula_section = _report_section(
        report,
        "## 3. Proposed Formulas For Formula Recommendations",
    )
    assert "### 10-K" in formula_section
    assert "### 10-Q" in formula_section
    assert "Formula" in formula_section
    assert "accounts_receivable = Revenues" in formula_section
    assert "all active" not in formula_section
    assert "us-gaap:" not in formula_section
    assert "custom:" not in formula_section
    assert "Recommendation" not in formula_section
    assert "Target concept" not in formula_section
    assert "Components" not in formula_section
    assert "/ duration / USD / 10-K" not in formula_section
    assert "/ instant / USD / 10-K" not in formula_section
    assert "/ instant / USD / 10-Q" not in formula_section
    assert "found_target" not in report
    assert "validated_component_pool" in report
    assert "period-scoped formula contexts" not in report
    assert "Metric-First Coverage Resolution" not in report
    assert "cap_per_target" not in report
    assert "generated_new" not in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
<<<<<<< HEAD
    assert output == ""
    assert "accounts_receivable = 0" in report
    assert "Zero-target evidence rows" in report
    assert "validated_zero_evidence_pool" in report
=======
    _assert_formula_progress_output(output)
    assert "target_zero" not in report
    assert "target_is_zero" not in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "## 3. Proposed Formulas For Formula Recommendations" in report
    formula_section = _report_section(
        report,
        "## 3. Proposed Formulas For Formula Recommendations",
    )
    assert "zero" in formula_section
    assert "## 4. Final Recommendations For Missing Targets" not in report
    assert "accounts_receivable = 0" in formula_section
    assert "validated_zero_evidence_pool" in report
    assert "review zero evidence" not in report
    assert "Zero-target evidence rows" in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
    _assert_formula_progress_output(output)
    assert len(provider_calls) == 1
<<<<<<< HEAD
    assert "Formula diagnostics run" in report
    assert "Formula proposals returned" in report
    assert "provider_failed" not in report
    assert "test provider failure" not in report
=======
    assert "provider_failed" not in report
    assert "test provider failure" not in report
    assert "No rows to display." in _report_section(
        report,
        "## 3. Proposed Formulas For Formula Recommendations",
    )


def test_milestone25_formula_proposal_fact_pool_uses_active_filing_periods_only(
    tmp_path: Path,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    with connect_sqlite(db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        raw_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(
                cik="0000000001",
                name="Test Company",
                ticker="TEST",
            )
        )
        assert company.company_id is not None
        filing_repository.upsert_filings(
            company.company_id,
            [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="active-10k",
                    form_type="10-K",
                    filing_date=date(2025, 2, 15),
                    fiscal_year=2025,
                    fiscal_period="FY",
                    is_active_window=True,
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="inactive-10k",
                    form_type="10-K",
                    filing_date=date(2020, 2, 15),
                    fiscal_year=2020,
                    fiscal_period="FY",
                    is_active_window=False,
                ),
            ],
        )
        raw_repository.upsert_facts(
            [
                _fact(
                    form="10-K",
                    accession_number="active-10k",
                    concept="ActiveCurrentPeriodConcept",
                    fiscal_year=2025,
                    fiscal_period="FY",
                ),
                _fact(
                    form="10-K",
                    accession_number="active-10k",
                    concept="ActiveFilingComparativeConcept",
                    fiscal_year=2024,
                    fiscal_period="FY",
                ),
                _fact(
                    form="10-K",
                    accession_number="inactive-10k",
                    concept="InactiveHistoricalConcept",
                    fiscal_year=2020,
                    fiscal_period="FY",
                ),
            ]
        )

        fact_pool = experiment._formula_proposal_fact_pool(
            connection,
            company_id=company.company_id,
            cik="0000000001",
            target_raw_fact_coverage=[],
        )

    assert [fact.concept for fact in fact_pool] == ["ActiveCurrentPeriodConcept"]
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)


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
            "--no-formula-proposals",
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
<<<<<<< HEAD
    assert "10-Q test-10q-new" in report
    assert "10-Q check due" in report
    assert "next check date before session: 2020-01-01" in report
=======
    assert "10-Q accession test-10q-new" in report
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)


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
<<<<<<< HEAD
                        concept="CustomerRevenueApproved",
                        label="Customer revenue approved",
                    ),
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
=======
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
                        concept="CustomUnmappedDisclosure",
                        label="Custom unmapped disclosure",
                    ),
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        taxonomy="custom",
                        concept="CustomerAccountsReceivable",
                        label="Customer accounts receivable",
                        period_type="instant",
                    ),
                    _fact(
                        form="10-Q",
                        accession_number="test-10q",
                        taxonomy="custom",
                        concept="CustomerAccountsReceivable",
                        label="Customer accounts receivable",
                        period_type="instant",
                        fiscal_period="Q1",
                        start_date=None,
                        end_date=date(2025, 3, 31),
                        filed_date=date(2025, 5, 15),
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
<<<<<<< HEAD
<<<<<<< HEAD
=======
                    ConceptMappingRecord(
                        taxonomy="custom",
                        concept="CustomerRevenueGross",
                        metric_name="revenue",
                        statement_type="income_statement",
                        scope_type=MAPPING_SCOPE_COMPANY,
                        scope_value="0000000001",
                        status=MAPPING_STATUS_CANDIDATE,
                        confidence=0.91,
                        match_method="semantic_candidate_embedding_v2",
                        evidence={
                            "embedding_granularity": "target_xbrl_concept_candidate",
                            "target_candidate_taxonomy": "us-gaap",
                            "target_candidate_xbrl_concept": (
                                "RevenueFromContractWithCustomerExcludingAssessedTax"
                            ),
                            "target_candidate_industry_labels": ["Common Base"],
                            "observed_label": "Customer revenue gross",
                            "observed_period_types": ["duration"],
                            "semantic_similarity": 0.91,
                            "requires_review": True,
                        },
                    ),
                    ConceptMappingRecord(
                        taxonomy="custom",
                        concept="CustomerAccountsReceivable",
                        metric_name="accounts_receivable",
                        statement_type="balance_sheet",
                        scope_type=MAPPING_SCOPE_COMPANY,
                        scope_value="0000000001",
                        status=MAPPING_STATUS_CANDIDATE,
                        confidence=0.88,
                        match_method="semantic_candidate_embedding_v2",
                        evidence={
                            "embedding_granularity": "target_xbrl_concept_candidate",
                            "target_candidate_taxonomy": "us-gaap",
                            "target_candidate_xbrl_concept": "AccountsReceivableNetCurrent",
                            "target_candidate_industry_labels": ["Common Base"],
                            "observed_label": "Customer accounts receivable",
                            "observed_period_types": ["instant"],
                            "semantic_similarity": 0.88,
                            "requires_review": True,
                        },
                    ),
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
=======
>>>>>>> 22949cb (Remove obsolete milestone 2.5 artifacts)
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
<<<<<<< HEAD
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
=======
    period_type: str = "duration",
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    start_date: date | None = date(2024, 1, 1),
    end_date: date | None = date(2024, 12, 31),
    filed_date: date | None = date(2025, 2, 15),
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
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
<<<<<<< HEAD
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
=======
        start_date=start_date,
        end_date=end_date,
        period_type=period_type,
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=filed_date,
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
