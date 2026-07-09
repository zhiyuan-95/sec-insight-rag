"""Manual examination harness for the Plan 2.5 company ingestion workflow."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings, load_settings
from src.analyze.xbrl_formula_proposals import (
    default_formula_proposal_provider_configs,
    generate_formula_proposal,
)
from src.ingestion import (
    FilingNotFoundError,
    SecConfigurationError,
    SecIngestionError,
    TickerNotFoundError,
    ingest_company,
)
from src.processing.base_metrics import BASE_METRIC_MAPPINGS
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    industry_label_assignments_for_company,
)
from src.processing.mapping_catalog import (
    STATUS_FOUND_MAPPED,
    STATUS_FOUND_UNMAPPED,
    STATUS_MISSING_TARGET,
    mapping_candidates_by_key,
    target_facts_for_industry_labels,
)
from src.processing.metric_recovery import (
    COMPONENT_AMBIGUOUS,
    COMPONENT_ASSUMED_ZERO,
    COMPONENT_CANDIDATE_REVIEW_REQUIRED,
    COMPONENT_MAPPED,
    COMPONENT_MISSING_REQUIRED,
    DEBT_RECOVERY_FORMULAS,
    SKIP_DUPLICATE_COMPONENT_FACTS,
    SKIP_PERIOD_MISMATCH,
    SKIP_UNIT_MISMATCH,
    TARGET_DECOMPOSITION_INCOMPLETE,
    TARGET_DERIVED_FROM_COMPONENTS,
    TARGET_DIRECT_MAPPED,
    MetricRecoveryResult,
    MetricRecoverySource,
    recover_debt_metrics,
)
from src.processing.formula_proposals import (
    CACHE_STATUS_ENTRY_INVALID,
    CACHE_STATUS_GENERATED_NEW,
    CACHE_STATUS_REUSED_EXACT_CONTEXT,
    CACHE_STATUS_REUSED_VALIDATION_FAILED,
    CACHE_STATUS_UNAVAILABLE,
    CONSENSUS_VALIDATED,
    CONSENSUS_TARGET_ZERO,
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_NO_FORMULA,
    PROVIDER_STATUS_PROPOSED,
    PROVIDER_STATUS_TARGET_ZERO,
    PROVIDER_STATUS_UNAVAILABLE,
    VALIDATION_STATUS_VALIDATED,
    VALIDATION_STATUS_ZERO_EVIDENCE,
    FormulaProposalFact,
    FormulaProposalContext,
    FormulaProposalProviderResult,
    FormulaProposalTarget,
    FormulaProposalValidationResult,
    build_formula_proposal_contexts,
    consensus_label,
    formula_context_fingerprint,
    formula_context_prompt_payload,
    load_formula_proposal_cache,
    save_formula_proposal_cache,
    validate_formula_proposal,
)
from src.storage import CompanyRepository, connect_sqlite, initialize_database

EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "MS2_5"
EXPERIMENT_STORAGE_DIR = PROJECT_ROOT / "experiments" / "storage"
DEFAULT_DB_PATH = EXPERIMENT_STORAGE_DIR / "experiment.db"
DEFAULT_REPORT_PREFIX = "milestone25_mapping_report"
DEFAULT_FILINGS_DIR = EXPERIMENT_STORAGE_DIR / "filings"
DEFAULT_EXPORTS_DIR = PROJECT_ROOT / "data" / "exports" / "ms2_5"
FORMULA_PROPOSAL_CACHE_SUBDIR = "formula_proposals"
FORMULA_PROPOSAL_CONTEXT_LIMIT_PER_TARGET = 1
FORMS = ("10-K", "10-Q")
STATUS_FOUND_MAPPED_ALTERNATE = "found_mapped_alternate"
MARKDOWN_CELL_MAX_CHARS = 120

TARGET_COVERAGE_REPORT_COLUMNS = (
    "industry_label",
    "target_xbrl_concept",
    "internal_metric_name",
    "alternate_mapped_concepts",
    "notes",
)
DEBT_RECOVERY_COMPONENT_POLICY = {
    (formula.formula_name, component.component_name): component
    for formula in DEBT_RECOVERY_FORMULAS
    for component in formula.components
}
PRESENTATION_NUMBER_EXCLUDED_HEADERS = {
    "accession",
    "accession_number",
    "cik",
    "company_id",
    "end_date",
    "filed_at",
    "filing_date",
    "filing_id",
    "fiscal_period",
    "fiscal_year",
    "year",
    "frame",
    "id",
    "local_path",
    "mapping_id",
    "metric_id",
    "next_check_date_10k",
    "next_check_date_10q",
    "raw_fact_id",
    "sic",
    "scope_value",
    "source_raw_fact_id",
    "start_date",
    "value",
}
PRESENTATION_NUMBER_SUFFIXES = (
    (Decimal("1000000000000"), "T"),
    (Decimal("1000000000"), "B"),
    (Decimal("1000000"), "M"),
    (Decimal("1000"), "K"),
)


@dataclass(frozen=True)
class ExperimentPaths:
    """Stable file locations used by the experiment."""

    database: Path
    report: Path
    filings_dir: Path
    exports_dir: Path


@dataclass(frozen=True)
class FilingUpdateEvidence:
    """One filing that became newly local during the already-ingested check."""

    form_type: str
    accession_number: str
    filing_date: str
    fiscal_year: int | None
    fiscal_period: str | None
    local_path: str


@dataclass(frozen=True)
class SessionDecision:
    """Observed decision path for a company that is already in local storage."""

    company_exists: bool
    status: str
    sec_checked: bool
    refresh_due_10k: bool | None
    refresh_due_10q: bool | None
    new_filings: tuple[FilingUpdateEvidence, ...]


@dataclass(frozen=True)
class ExperimentRun:
    """All evidence needed to render the Markdown report."""

    ticker: str
    run_timestamp: str
    sec_user_agent_configured: bool
    paths: ExperimentPaths
    company_existed_before_setup: bool
    setup_status: str
    setup_sec_checked: bool
    setup_snapshot: dict[str, Any]
    session_before_snapshot: dict[str, Any]
    session_after_snapshot: dict[str, Any]
    session_decision: SessionDecision
    warnings: tuple[str, ...] = ()
    error: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Milestone 2.5 experiment and write inspection artifacts."""
    args = _parse_args(argv)
    ticker = args.ticker.strip().upper()
    paths = _paths_from_args(args)
    settings: Settings | None = None

    try:
        settings = _experiment_settings(args.env_file, paths)
        if not settings.sec_user_agent:
            raise SecConfigurationError("SEC_USER_AGENT is required for live SEC experiment runs")
        run = run_experiment(
            ticker=ticker,
            settings=settings,
            paths=paths,
            formula_proposals_enabled=args.formula_proposals,
            formula_proposal_target_limit=args.formula_proposal_target_limit,
        )
    except (SecConfigurationError, SecIngestionError, TickerNotFoundError, FilingNotFoundError, ValueError) as exc:
        run = _error_run(
            ticker=ticker,
            paths=paths,
            error=exc,
            sec_user_agent_configured=bool(settings and settings.sec_user_agent),
        )
        _present_report(run, write_report=args.write_report, full_report=args.full_report)
        return 1

    artifact_warnings = [
        *_export_csv_artifacts(
            paths,
            company_id=_snapshot_company_id(run.session_after_snapshot),
        ),
    ]
    if artifact_warnings:
        run = replace(run, warnings=tuple(dict.fromkeys([*run.warnings, *artifact_warnings])))
    _present_report(run, write_report=args.write_report, full_report=args.full_report)
    return 0


def run_experiment(
    *,
    ticker: str,
    settings: Settings,
    paths: ExperimentPaths,
    formula_proposals_enabled: bool = False,
    formula_proposal_target_limit: int | None = None,
) -> ExperimentRun:
    """Run ingestion against steady experiment storage, then inspect the local session path."""
    run_timestamp = datetime.now(timezone.utc).isoformat()
    normalized_ticker = _normalize_ticker(ticker)

    company_existed_before_setup = _company_exists(paths.database, normalized_ticker)
    setup_result = ingest_company(normalized_ticker, settings)
    setup_snapshot = _snapshot(paths.database, normalized_ticker)

    session_before_snapshot = setup_snapshot
    session_company_exists = bool(session_before_snapshot.get("company"))
    if session_company_exists:
        session_result = ingest_company(normalized_ticker, settings)
        session_after_snapshot = _snapshot(
            paths.database,
            normalized_ticker,
            settings=settings,
            formula_proposals_enabled=formula_proposals_enabled,
            formula_proposal_target_limit=formula_proposal_target_limit,
        )
        session_decision = SessionDecision(
            company_exists=True,
            status=session_result.status,
            sec_checked=session_result.sec_checked,
            refresh_due_10k=session_result.refresh_due_10k,
            refresh_due_10q=session_result.refresh_due_10q,
            new_filings=_new_filing_evidence(session_before_snapshot, session_after_snapshot),
        )
        warnings = tuple(dict.fromkeys([*setup_result.warnings, *session_result.warnings]))
    else:
        session_after_snapshot = session_before_snapshot
        session_decision = SessionDecision(
            company_exists=False,
            status="company_not_in_local_storage",
            sec_checked=False,
            refresh_due_10k=None,
            refresh_due_10q=None,
            new_filings=(),
        )
        warnings = tuple(setup_result.warnings)

    return ExperimentRun(
        ticker=normalized_ticker,
        run_timestamp=run_timestamp,
        sec_user_agent_configured=bool(settings.sec_user_agent),
        paths=paths,
        company_existed_before_setup=company_existed_before_setup,
        setup_status=setup_result.status,
        setup_sec_checked=setup_result.sec_checked,
        setup_snapshot=setup_snapshot,
        session_before_snapshot=session_before_snapshot,
        session_after_snapshot=session_after_snapshot,
        session_decision=session_decision,
        warnings=warnings,
        error=None,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a manual examination report for the Plan 2.5 ingestion workflow.",
    )
    parser.add_argument("--ticker", required=True, help="Single company ticker to inspect.")
    parser.add_argument("--env-file", default="config.env", help="Environment file containing SEC_USER_AGENT.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help=argparse.SUPPRESS)
    parser.add_argument("--report-path", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--filings-dir", default=str(DEFAULT_FILINGS_DIR), help=argparse.SUPPRESS)
    parser.add_argument("--exports-dir", default=str(DEFAULT_EXPORTS_DIR), help=argparse.SUPPRESS)
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Accepted for compatibility; the experiment report is always saved.",
    )
    parser.add_argument(
        "--full-report",
        action="store_true",
        help="Include detailed Markdown sections with compact table samples in the saved report.",
    )
    formula_group = parser.add_mutually_exclusive_group()
    formula_group.add_argument(
        "--formula-proposals",
        dest="formula_proposals",
        action="store_true",
        default=True,
        help="Accepted for compatibility; formula proposals run by default.",
    )
    formula_group.add_argument(
        "--no-formula-proposals",
        dest="formula_proposals",
        action="store_false",
        help="Skip report-only missing-target formula proposal provider calls.",
    )
    parser.add_argument(
        "--formula-proposal-target-limit",
        type=int,
        default=None,
        help="Limit missing targets sent to the formula proposal panel; omit to evaluate all.",
    )
    return parser.parse_args(argv)


def _paths_from_args(args: argparse.Namespace) -> ExperimentPaths:
    return ExperimentPaths(
        database=Path(args.db_path),
        report=Path(args.report_path) if args.report_path else _default_report_path(args.ticker),
        filings_dir=Path(args.filings_dir),
        exports_dir=Path(args.exports_dir),
    )


def _default_report_path(ticker: str) -> Path:
    ticker_slug = _safe_ticker_slug(ticker)
    return EXPERIMENT_DIR / f"{DEFAULT_REPORT_PREFIX}_{ticker_slug}.md"


def _safe_ticker_slug(ticker: str) -> str:
    normalized = ticker.strip().upper()
    safe_chars = [
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in normalized
    ]
    return "".join(safe_chars).strip("-_.") or "UNKNOWN"


def _experiment_settings(env_file: str, paths: ExperimentPaths) -> Settings:
    base_settings = load_settings(env_file)
    return base_settings.model_copy(
        update={
            "stock_sql_db_path": paths.database,
            "stock_filings_base_dir": paths.filings_dir,
        }
    )


def _normalize_ticker(ticker: str) -> str:
    value = ticker.strip().upper()
    if not value:
        raise ValueError("Ticker is required")
    if any(char.isspace() for char in value):
        raise ValueError(f"Ticker must be a single symbol, received: {ticker!r}")
    return value


def _company_exists(database: Path, ticker: str) -> bool:
    if not database.exists():
        return False
    with connect_sqlite(database) as connection:
        initialize_database(connection)
        return CompanyRepository(connection).get_by_ticker(ticker) is not None


def _snapshot(
    database: Path,
    ticker: str,
    *,
    settings: Settings | None = None,
    formula_proposals_enabled: bool = False,
    formula_proposal_target_limit: int | None = None,
) -> dict[str, Any]:
    if not database.exists():
        return _empty_snapshot()

    with connect_sqlite(database) as connection:
        initialize_database(connection)
        company = _fetch_one(
            connection,
            """
            SELECT *
            FROM companies
            WHERE ticker = ? COLLATE NOCASE
            ORDER BY company_id
            LIMIT 1
            """,
            [ticker],
        )
        company_id = company.get("company_id") if company else None
        cik = company.get("cik") if company else None
        observed_concepts = _observed_raw_concepts(connection, cik)
        industry_assignment = _company_industry_label_assignment(
            connection,
            company,
            observed_concepts,
        )
        target_raw_fact_coverage = _target_raw_fact_coverage(
            connection,
            company_id=company_id,
            cik=cik,
            assignment=industry_assignment,
        )
        approved_learned_mappings = _learned_mapping_rows(
            connection,
            cik,
            status="approved",
        )
        unknown_xbrl_concepts = _unknown_xbrl_concepts(connection, company_id, cik)
        debt_recovery_results = _debt_recovery_results(
            connection,
            company_id=company_id,
        )
        formula_proposal_snapshot = _formula_proposal_snapshot(
            connection,
            ticker=ticker,
            cik=cik,
            company_id=company_id,
            target_raw_fact_coverage=target_raw_fact_coverage,
            enabled=formula_proposals_enabled,
            settings=settings,
            target_limit=formula_proposal_target_limit,
        )
        return {
            "company": company,
            "counts": _table_counts(connection),
            "filings": _filing_rows(connection, company_id),
            "filings_by_form": _accessions_by_form(connection, company_id),
            "active_filings_by_form": _active_filing_counts_by_form(connection, company_id),
            "company_industry_labels": _company_industry_label_rows(company, industry_assignment),
            "target_raw_fact_coverage": target_raw_fact_coverage,
            "found_target_facts": _target_rows_with_status(target_raw_fact_coverage, STATUS_FOUND_MAPPED),
            "missing_target_facts": _target_rows_with_status(target_raw_fact_coverage, STATUS_MISSING_TARGET),
            "found_unmapped_target_facts": _target_rows_with_status(target_raw_fact_coverage, STATUS_FOUND_UNMAPPED),
            "debt_recovery_formula_catalog": _debt_recovery_formula_catalog_rows(),
            "debt_recovery_summary": _debt_recovery_summary_rows(debt_recovery_results),
            "debt_recovery_diagnostics": _debt_recovery_result_rows(debt_recovery_results),
            "debt_recovery_components": _debt_recovery_component_rows(debt_recovery_results),
            "formula_proposal_summary": formula_proposal_snapshot["summary"],
            "formula_proposal_diagnostics": formula_proposal_snapshot["diagnostics"],
            "formula_proposal_components": formula_proposal_snapshot["components"],
            "formula_proposal_fact_pool_summary": formula_proposal_snapshot["fact_pool_summary"],
            "metric_counts_by_statement": _metric_counts_by_statement(connection, company_id),
            "metric_lineage_summary": _metric_lineage_summary(connection, company_id),
            "raw_fact_mapping_coverage": _raw_fact_mapping_coverage(connection, company_id, cik),
            "alternate_xbrl_tags": _alternate_xbrl_tags(connection, company_id),
            "unknown_xbrl_concepts": unknown_xbrl_concepts,
            "inline_xbrl_coverage": _inline_xbrl_coverage(connection, cik),
            "xbrl_concept_counts_by_period": _xbrl_concept_counts_by_period(connection, cik),
            "mapping_profile_reuse": _mapping_profile_reuse_rows(
                assignment=industry_assignment,
                target_raw_fact_coverage=target_raw_fact_coverage,
                approved_learned_mappings=approved_learned_mappings,
                unknown_xbrl_concepts=unknown_xbrl_concepts,
            ),
            "approved_learned_mappings": approved_learned_mappings,
            "metric_sample": _metric_sample(connection, company_id),
            "traceability_sample": _traceability_sample(connection, company_id),
            "quality_flags": _quality_flags(connection, cik),
        }


def _empty_snapshot() -> dict[str, Any]:
    return {
        "company": {},
        "counts": {
            "companies": 0,
            "company_industry_labels": 0,
            "filings": 0,
            "raw_xbrl_facts": 0,
            "xbrl_concept_mappings": 0,
            "financial_metrics": 0,
        },
        "filings": [],
        "filings_by_form": {form_type: () for form_type in FORMS},
        "active_filings_by_form": {form_type: 0 for form_type in FORMS},
        "company_industry_labels": [],
        "target_raw_fact_coverage": [],
        "found_target_facts": [],
        "missing_target_facts": [],
        "found_unmapped_target_facts": [],
        "debt_recovery_formula_catalog": _debt_recovery_formula_catalog_rows(),
        "debt_recovery_summary": [],
        "debt_recovery_diagnostics": [],
        "debt_recovery_components": [],
        "formula_proposal_summary": _formula_proposal_not_run_summary(),
        "formula_proposal_diagnostics": [],
        "formula_proposal_components": [],
        "formula_proposal_fact_pool_summary": [],
        "metric_counts_by_statement": [],
        "metric_lineage_summary": [],
        "raw_fact_mapping_coverage": [],
        "alternate_xbrl_tags": [],
        "unknown_xbrl_concepts": [],
        "inline_xbrl_coverage": [],
        "xbrl_concept_counts_by_period": [],
        "mapping_profile_reuse": [],
        "approved_learned_mappings": [],
        "metric_sample": [],
        "traceability_sample": [],
        "quality_flags": (),
    }


def _snapshot_company_id(snapshot: dict[str, Any]) -> int | None:
    company = snapshot.get("company") or {}
    company_id = company.get("company_id")
    return int(company_id) if company_id is not None else None


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
        for table in (
            "companies",
            "company_industry_labels",
            "filings",
            "raw_xbrl_facts",
            "xbrl_concept_mappings",
            "financial_metrics",
        )
    }


def _filing_rows(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            form_type,
            accession_number,
            filing_date,
            report_date,
            fiscal_year,
            fiscal_period,
            is_active_window,
            local_path
        FROM filings
        WHERE company_id = ?
        ORDER BY form_type, filing_date DESC, accession_number DESC
        """,
        [company_id],
    )


def _accessions_by_form(connection: sqlite3.Connection, company_id: int | None) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, tuple[str, ...]] = {form_type: () for form_type in FORMS}
    if company_id is None:
        return grouped
    rows = _fetch_all(
        connection,
        """
        SELECT form_type, accession_number
        FROM filings
        WHERE company_id = ?
        ORDER BY filing_date DESC, accession_number DESC
        """,
        [company_id],
    )
    for form_type in FORMS:
        grouped[form_type] = tuple(row["accession_number"] for row in rows if row["form_type"] == form_type)
    return grouped


def _new_filing_evidence(
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
) -> tuple[FilingUpdateEvidence, ...]:
    before_accessions = {
        row["accession_number"]
        for row in before_snapshot.get("filings", [])
        if row.get("accession_number")
    }
    new_rows = [
        row
        for row in after_snapshot.get("filings", [])
        if row.get("accession_number") and row["accession_number"] not in before_accessions
    ]
    return tuple(
        FilingUpdateEvidence(
            form_type=str(row.get("form_type") or ""),
            accession_number=str(row.get("accession_number") or ""),
            filing_date=str(row.get("filing_date") or "not available"),
            fiscal_year=row.get("fiscal_year"),
            fiscal_period=row.get("fiscal_period"),
            local_path=str(row.get("local_path") or "not available"),
        )
        for row in new_rows
    )


def _active_filing_counts_by_form(connection: sqlite3.Connection, company_id: int | None) -> dict[str, int]:
    grouped = {form_type: 0 for form_type in FORMS}
    if company_id is None:
        return grouped
    rows = _fetch_all(
        connection,
        """
        SELECT form_type, COUNT(*) AS count
        FROM filings
        WHERE company_id = ? AND is_active_window = 1
        GROUP BY form_type
        """,
        [company_id],
    )
    for row in rows:
        grouped[row["form_type"]] = int(row["count"])
    return grouped


def _observed_raw_concepts(connection: sqlite3.Connection, cik: str | None) -> tuple[str, ...]:
    if not cik:
        return ()
    rows = _fetch_all(
        connection,
        """
        SELECT DISTINCT concept
        FROM raw_xbrl_facts
        WHERE cik = ? AND concept IS NOT NULL
        ORDER BY concept
        """,
        [cik],
    )
    return tuple(str(row["concept"]) for row in rows if row.get("concept"))


def _xbrl_concept_counts_by_period(connection: sqlite3.Connection, cik: str | None) -> list[dict[str, Any]]:
    if not cik:
        return []
    return _fetch_all(
        connection,
        """
        WITH normalized_facts AS (
            SELECT
                CASE
                    WHEN UPPER(form) IN ('10-K', '10-K/A') THEN '10-K'
                    WHEN UPPER(form) IN ('10-Q', '10-Q/A') THEN '10-Q'
                    ELSE NULL
                END AS form_type,
                fiscal_year,
                CASE
                    WHEN UPPER(form) IN ('10-K', '10-K/A') THEN 'FY'
                    ELSE UPPER(fiscal_period)
                END AS fiscal_period,
                taxonomy || ':' || concept AS concept_key
            FROM raw_xbrl_facts
            WHERE cik = ?
              AND fiscal_year IS NOT NULL
              AND taxonomy IS NOT NULL
              AND concept IS NOT NULL
              AND UPPER(form) IN ('10-K', '10-K/A', '10-Q', '10-Q/A')
        )
        SELECT
            form_type,
            fiscal_year,
            fiscal_period,
            COUNT(DISTINCT concept_key) AS concept_count
        FROM normalized_facts
        WHERE form_type IS NOT NULL
          AND fiscal_period IS NOT NULL
        GROUP BY form_type, fiscal_year, fiscal_period
        ORDER BY form_type, fiscal_year, fiscal_period
        """,
        [cik],
    )


def _company_industry_label_assignment(
    connection: sqlite3.Connection,
    company: dict[str, Any],
    observed_concepts: Sequence[str],
) -> CompanyIndustryLabelAssignment:
    company_id = company.get("company_id")
    if company_id is not None:
        rows = _fetch_all(
            connection,
            """
            SELECT *
            FROM company_industry_labels
            WHERE company_id = ? AND status = 'approved'
            ORDER BY industry_label
            """,
            [company_id],
        )
        if rows:
            evidence = tuple(
                dict.fromkeys(
                    item
                    for row in rows
                    for item in json.loads(row.get("evidence_json") or "[]")
                )
            )
            return CompanyIndustryLabelAssignment(
                ticker=str(company.get("ticker") or "").upper(),
                cik=str(company.get("cik") or ""),
                assigned_industry_labels=tuple(
                    str(row["industry_label"]) for row in rows
                ),
                assignment_source=_join(
                    sorted({str(row["assignment_source"]) for row in rows})
                ),
                assignment_reason=" ; ".join(
                    dict.fromkeys(str(row["assignment_reason"]) for row in rows)
                ),
                supporting_evidence=evidence,
                reviewed_at=max(
                    (str(row.get("reviewed_at") or "") for row in rows),
                    default="",
                ),
                label_status="assigned",
                notes="Persisted reusable company industry labels.",
            )
    return industry_label_assignments_for_company(
        company.get("ticker"),
        company.get("cik"),
        sic=company.get("sic"),
        sic_description=company.get("sic_description"),
        observed_concepts=observed_concepts,
    )


def _company_industry_label_rows(
    company: dict[str, Any],
    assignment: CompanyIndustryLabelAssignment,
) -> list[dict[str, Any]]:
    if not company:
        return []
    return [
        {
            "ticker": assignment.ticker,
            "cik": assignment.cik,
            "sic": company.get("sic") or "",
            "sic_description": company.get("sic_description") or "",
            "assigned_industry_labels": _join(assignment.assigned_industry_labels),
            "assignment_source": assignment.assignment_source,
            "assignment_reason": assignment.assignment_reason,
            "supporting_evidence": " ; ".join(assignment.supporting_evidence),
            "label_status": assignment.label_status,
            "reviewed_at": assignment.reviewed_at,
            "notes": assignment.notes,
        }
    ]


def _target_raw_fact_coverage(
    connection: sqlite3.Connection,
    *,
    company_id: int | None,
    cik: str | None,
    assignment: CompanyIndustryLabelAssignment,
) -> list[dict[str, Any]]:
    if company_id is None or not cik:
        return []
    targets = target_facts_for_industry_labels(assignment.assigned_industry_labels)
    target_keys = tuple(dict.fromkeys((target.taxonomy, target.raw_concept) for target in targets))
    target_clause = ", ".join("(?, ?)" for _ in target_keys)
    target_params = [value for key in target_keys for value in key]
    observed_by_key = {
        (str(row["taxonomy"]), str(row["concept"])): row
        for row in _fetch_all(
            connection,
            f"""
            SELECT
                taxonomy,
                concept,
                COUNT(*) AS observed_rows,
                MAX(filed_date) AS latest_filing_date,
                COUNT(DISTINCT unit) AS unit_count,
                COALESCE(GROUP_CONCAT(DISTINCT form), '') AS forms
            FROM raw_xbrl_facts
            WHERE cik = ? AND (taxonomy, concept) IN ({target_clause})
            GROUP BY taxonomy, concept
            """,
            [cik, *target_params],
        )
    }
    mapped_by_key = {
        (str(row["taxonomy"]), str(row["concept"])): int(row["mapped_rows"])
        for row in _fetch_all(
            connection,
            f"""
            SELECT
                f.taxonomy,
                f.concept,
                COUNT(*) AS mapped_rows
            FROM financial_metrics AS m
            INNER JOIN raw_xbrl_facts AS f
                ON f.id = m.raw_fact_id
            WHERE m.company_id = ? AND (f.taxonomy, f.concept) IN ({target_clause})
            GROUP BY f.taxonomy, f.concept
            """,
            [company_id, *target_params],
        )
    }
    mapped_by_metric = {
        str(row["metric_name"]): row
        for row in _fetch_all(
            connection,
            """
            SELECT
                m.metric_name,
                COUNT(*) AS mapped_rows,
                COALESCE(
                    GROUP_CONCAT(DISTINCT f.taxonomy || ':' || f.concept),
                    ''
                ) AS mapped_concepts
            FROM financial_metrics AS m
            LEFT JOIN raw_xbrl_facts AS f
                ON f.id = m.raw_fact_id
            WHERE m.company_id = ?
            GROUP BY m.metric_name
            """,
            [company_id],
        )
    }
    label_review_note = (
        "industry-specific targets are not included until a source-controlled label is assigned"
        if assignment.label_status == "needs_label_review"
        else ""
    )
    rows: list[dict[str, Any]] = []
    for target in targets:
        key = (target.taxonomy, target.raw_concept)
        observed = observed_by_key.get(key, {})
        observed_rows = int(observed.get("observed_rows") or 0)
        mapped_rows = mapped_by_key.get(key, 0)
        status = _target_coverage_status(observed_rows, mapped_rows)
        alternate_mapping = mapped_by_metric.get(target.internal_metric_name, {})
        alternate_mapped_rows = int(alternate_mapping.get("mapped_rows") or 0)
        if status == STATUS_MISSING_TARGET and alternate_mapped_rows > 0:
            status = STATUS_FOUND_MAPPED_ALTERNATE
        notes = "; ".join(
            note
            for note in (
                target.notes,
                label_review_note,
                "observed but did not create financial_metrics rows" if status == STATUS_FOUND_UNMAPPED else "",
                (
                    "canonical metric recovered through an approved alternate XBRL concept"
                    if status == STATUS_FOUND_MAPPED_ALTERNATE
                    else ""
                ),
            )
            if note
        )
        rows.append(
            {
                "industry_label": target.industry_label,
                "target_xbrl_concept": f"{target.taxonomy}:{target.raw_concept}",
                "target_raw_concept": target.raw_concept,
                "taxonomy": target.taxonomy,
                "internal_metric_name": target.internal_metric_name,
                "statement_type": target.statement_type,
                "required_for_core": _yes_no(target.required_for_core),
                "required_for_specialized_indicators": _yes_no(target.required_for_specialized_indicators),
                "status": status,
                "observed_rows": observed_rows,
                "mapped_rows": mapped_rows,
                "alternate_mapped_rows": alternate_mapped_rows,
                "alternate_mapped_concepts": alternate_mapping.get("mapped_concepts") or "",
                "unit_count": observed.get("unit_count") or 0,
                "forms": observed.get("forms") or "",
                "latest_filing_date": observed.get("latest_filing_date") or "",
                "notes": notes,
            }
        )
    return rows


def _formula_proposal_snapshot(
    connection: sqlite3.Connection,
    *,
    ticker: str,
    cik: str | None,
    company_id: int | None,
    target_raw_fact_coverage: list[dict[str, Any]],
    enabled: bool,
    settings: Settings | None,
    target_limit: int | None,
) -> dict[str, list[dict[str, Any]]]:
    if not enabled:
        return {
            "summary": _formula_proposal_not_run_summary(),
            "diagnostics": [],
            "components": [],
            "fact_pool_summary": [],
        }
    if company_id is None or not cik:
        return {
            "summary": _formula_proposal_status_summary(
                status="not_available",
                notes="Company was not available in local storage.",
            ),
            "diagnostics": [],
            "components": [],
            "fact_pool_summary": [],
        }

    targets = _formula_proposal_targets(target_raw_fact_coverage, target_limit=target_limit)
    fact_pool = _formula_proposal_fact_pool(
        connection,
        company_id=company_id,
        cik=cik,
        target_raw_fact_coverage=target_raw_fact_coverage,
    )
    fact_pool_summary = _formula_proposal_fact_pool_summary_rows(fact_pool)
    if not targets:
        return {
            "summary": _formula_proposal_status_summary(
                status="no_missing_targets",
                notes="No missing target concepts remained after existing mapping stages.",
            ),
            "diagnostics": [],
            "components": [],
            "fact_pool_summary": fact_pool_summary,
        }
    if not fact_pool:
        return {
            "summary": _formula_proposal_status_summary(
                status="no_eligible_raw_fact_pool",
                notes="No numeric raw XBRL facts were available for formula proposals.",
            ),
            "diagnostics": [],
            "components": [],
            "fact_pool_summary": [],
        }

    provider_configs = _formula_proposal_provider_configs(settings)
    cache_dir = _formula_proposal_cache_dir(settings)
    diagnostics: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    consensus_counts: dict[str, int] = {}
    run_provider_results: dict[str, tuple[FormulaProposalProviderResult, str, str]] = {}
    context_count = 0
    available_context_count = 0
    skipped_context_count = 0

    for target in targets:
        formula_contexts = build_formula_proposal_contexts(target=target, fact_pool=fact_pool)
        available_context_count += len(formula_contexts)
        if len(formula_contexts) > FORMULA_PROPOSAL_CONTEXT_LIMIT_PER_TARGET:
            skipped_context_count += len(formula_contexts) - FORMULA_PROPOSAL_CONTEXT_LIMIT_PER_TARGET
            formula_contexts = formula_contexts[:FORMULA_PROPOSAL_CONTEXT_LIMIT_PER_TARGET]
        if not formula_contexts:
            diagnostics.append(_formula_proposal_no_context_row(target))
            continue
        for formula_context in formula_contexts:
            context_count += 1
            provider_results: list[FormulaProposalProviderResult] = []
            cache_statuses: list[str] = []
            cache_warnings: list[str] = []
            context_hashes: list[str] = []
            for provider in provider_configs:
                formula_hash, fingerprint_payload = formula_context_fingerprint(
                    target=target,
                    context=formula_context,
                    provider_name=provider.provider_name,
                    model_name=provider.model_name,
                )
                context_hashes.append(formula_hash)
                run_cached = run_provider_results.get(formula_hash)
                if run_cached is not None:
                    result, cache_status, cache_warning = run_cached
                    provider_results.append(result)
                    cache_statuses.append(
                        CACHE_STATUS_REUSED_EXACT_CONTEXT
                        if cache_status == CACHE_STATUS_GENERATED_NEW
                        else cache_status
                    )
                    cache_warnings.append(cache_warning)
                    continue
                cached_result, cache_warning = load_formula_proposal_cache(
                    cache_dir=cache_dir,
                    formula_context_hash=formula_hash,
                    target=target,
                    provider_name=provider.provider_name,
                    model_name=provider.model_name,
                )
                if cached_result is not None:
                    provider_results.append(cached_result)
                    cache_statuses.append(CACHE_STATUS_REUSED_EXACT_CONTEXT)
                    cache_warnings.append(cache_warning)
                    run_provider_results[formula_hash] = (
                        cached_result,
                        CACHE_STATUS_REUSED_EXACT_CONTEXT,
                        cache_warning,
                    )
                    continue
                prompt_context = formula_context_prompt_payload(
                    context=formula_context,
                    formula_context_hash=formula_hash,
                )
                result = generate_formula_proposal(
                    ticker=ticker,
                    cik=cik,
                    target=target,
                    fact_pool=list(formula_context.prompt_fact_pool),
                    formula_context=prompt_context,
                    provider=provider,
                )
                provider_results.append(result)
                if result.provider_status in {
                    PROVIDER_STATUS_PROPOSED,
                    PROVIDER_STATUS_TARGET_ZERO,
                    PROVIDER_STATUS_NO_FORMULA,
                }:
                    write_warning = save_formula_proposal_cache(
                        cache_dir=cache_dir,
                        formula_context_hash=formula_hash,
                        fingerprint_payload=fingerprint_payload,
                        result=result,
                    )
                    cache_statuses.append(CACHE_STATUS_GENERATED_NEW)
                    result_cache_warning = cache_warning or write_warning
                    cache_warnings.append(result_cache_warning)
                    run_provider_results[formula_hash] = (
                        result,
                        CACHE_STATUS_GENERATED_NEW,
                        result_cache_warning,
                    )
                elif cache_warning:
                    cache_statuses.append(CACHE_STATUS_ENTRY_INVALID)
                    cache_warnings.append(cache_warning)
                    run_provider_results[formula_hash] = (
                        result,
                        CACHE_STATUS_ENTRY_INVALID,
                        cache_warning,
                    )
                else:
                    cache_statuses.append(CACHE_STATUS_UNAVAILABLE)
                    cache_warnings.append("")
                    run_provider_results[formula_hash] = (
                        result,
                        CACHE_STATUS_UNAVAILABLE,
                        "",
                    )
            provider_results_tuple = tuple(provider_results)
            validations = tuple(
                validate_formula_proposal(
                    target=target,
                    proposal=proposal,
                    fact_pool=formula_context.facts,
                    statement_relationship_by_key=formula_context.statement_relationship_by_key,
                )
                for proposal in provider_results_tuple
            )
            adjusted_cache_statuses = tuple(
                CACHE_STATUS_REUSED_VALIDATION_FAILED
                if cache_status == CACHE_STATUS_REUSED_EXACT_CONTEXT
                and (
                    (
                        proposal.provider_status == PROVIDER_STATUS_PROPOSED
                        and validation.validation_status != VALIDATION_STATUS_VALIDATED
                    )
                    or (
                        proposal.provider_status == PROVIDER_STATUS_TARGET_ZERO
                        and validation.validation_status != VALIDATION_STATUS_ZERO_EVIDENCE
                    )
                )
                else cache_status
                for cache_status, validation, proposal in zip(cache_statuses, validations, provider_results_tuple, strict=False)
            )
            agreement_label = consensus_label(provider_results_tuple, validations)
            consensus_counts[agreement_label] = consensus_counts.get(agreement_label, 0) + 1
            diagnostics.extend(
                _formula_proposal_diagnostic_rows(
                    target=target,
                    context=formula_context,
                    proposals=provider_results_tuple,
                    validations=validations,
                    agreement_label=agreement_label,
                    formula_context_hashes=tuple(context_hashes),
                    cache_statuses=adjusted_cache_statuses,
                    cache_warnings=tuple(cache_warnings),
                )
            )
            components.extend(
                _formula_proposal_component_rows(
                    target=target,
                    context=formula_context,
                    proposals=provider_results_tuple,
                )
            )

    return {
        "summary": _formula_proposal_summary_rows(
            targets=targets,
            fact_pool=fact_pool,
            diagnostics=diagnostics,
            consensus_counts=consensus_counts,
            target_limit=target_limit,
            context_count=context_count,
            available_context_count=available_context_count,
            skipped_context_count=skipped_context_count,
            cache_dir=cache_dir,
        ),
        "diagnostics": diagnostics,
        "components": components,
        "fact_pool_summary": fact_pool_summary,
    }


def _formula_proposal_not_run_summary() -> list[dict[str, Any]]:
    return _formula_proposal_status_summary(
        status="not_run",
        notes="Formula proposals were skipped for this run; omit --no-formula-proposals to call the report-only model panel.",
    )


def _formula_proposal_status_summary(*, status: str, notes: str) -> list[dict[str, Any]]:
    return [
        {
            "evidence_item": "formula proposal model panel",
            "value": status,
            "notes": notes,
        }
    ]


def _formula_proposal_targets(
    target_raw_fact_coverage: list[dict[str, Any]],
    *,
    target_limit: int | None,
) -> tuple[FormulaProposalTarget, ...]:
    rows = [
        row
        for row in target_raw_fact_coverage
        if row.get("status") == STATUS_MISSING_TARGET
    ]
    if target_limit is not None and target_limit > 0:
        rows = rows[:target_limit]
    targets: list[FormulaProposalTarget] = []
    for row in rows:
        targets.append(
            FormulaProposalTarget(
                target_metric_name=str(row.get("internal_metric_name") or ""),
                target_xbrl_concept=str(row.get("target_xbrl_concept") or ""),
                taxonomy=str(row.get("taxonomy") or ""),
                concept=str(row.get("target_raw_concept") or ""),
                statement_type=str(row.get("statement_type") or ""),
                industry_label=str(row.get("industry_label") or ""),
                notes=str(row.get("notes") or ""),
            )
        )
    return tuple(targets)


def _formula_proposal_fact_pool(
    connection: sqlite3.Connection,
    *,
    company_id: int,
    cik: str,
    target_raw_fact_coverage: list[dict[str, Any]],
) -> tuple[FormulaProposalFact, ...]:
    target_status_by_key = {
        (str(row.get("taxonomy") or ""), str(row.get("target_raw_concept") or "")): str(row.get("status") or "")
        for row in target_raw_fact_coverage
    }
    approved_alternate_keys = {
        (str(row.get("taxonomy") or ""), str(row.get("observed_raw_concept") or ""))
        for row in _learned_mapping_rows(connection, cik, status="approved")
    }
    rows = _fetch_all(
        connection,
        """
        SELECT
            f.id AS raw_fact_id,
            f.taxonomy,
            f.concept,
            COALESCE(f.label, '') AS label,
            f.value_numeric,
            f.unit,
            f.period_type,
            f.fiscal_year,
            f.fiscal_period,
            f.start_date,
            f.end_date,
            f.form,
            f.filed_date,
            f.accession_number,
            COALESCE(m.metric_name, '') AS mapped_metric_name,
            COALESCE(m.statement_type, '') AS mapped_statement_type
        FROM raw_xbrl_facts AS f
        LEFT JOIN financial_metrics AS m
            ON m.raw_fact_id = f.id AND m.company_id = ?
        WHERE f.cik = ?
          AND f.value_numeric IS NOT NULL
          AND (f.is_numeric IS NULL OR f.is_numeric = 1)
        ORDER BY f.taxonomy, f.concept, f.fiscal_year DESC, f.fiscal_period DESC, f.accession_number
        """,
        [company_id, cik],
    )
    facts: list[FormulaProposalFact] = []
    for row in rows:
        value = _parse_decimal_text(str(row.get("value_numeric") or ""))
        if value is None:
            continue
        taxonomy = str(row.get("taxonomy") or "")
        concept = str(row.get("concept") or "")
        facts.append(
            FormulaProposalFact(
                raw_fact_id=int(row["raw_fact_id"]),
                taxonomy=taxonomy,
                concept=concept,
                label=str(row.get("label") or ""),
                value_numeric=value,
                unit=str(row.get("unit") or ""),
                period_type=str(row.get("period_type") or ""),
                fiscal_year=row.get("fiscal_year"),
                fiscal_period=row.get("fiscal_period"),
                accession_number=str(row.get("accession_number") or ""),
                form=str(row.get("form") or ""),
                start_date=_date_from_text(row.get("start_date")),
                end_date=_date_from_text(row.get("end_date")),
                filed_date=_date_from_text(row.get("filed_date")),
                mapping_status=_formula_fact_mapping_status(
                    taxonomy=taxonomy,
                    concept=concept,
                    mapped_metric_name=str(row.get("mapped_metric_name") or ""),
                    target_status_by_key=target_status_by_key,
                    approved_alternate_keys=approved_alternate_keys,
                ),
                mapped_metric_name=str(row.get("mapped_metric_name") or ""),
                mapped_statement_type=str(row.get("mapped_statement_type") or ""),
            )
        )
    return tuple(facts)


def _formula_fact_mapping_status(
    *,
    taxonomy: str,
    concept: str,
    mapped_metric_name: str,
    target_status_by_key: dict[tuple[str, str], str],
    approved_alternate_keys: set[tuple[str, str]],
) -> str:
    key = (taxonomy, concept)
    if target_status_by_key.get(key) == STATUS_FOUND_MAPPED:
        return "found_target"
    if target_status_by_key.get(key) == STATUS_FOUND_UNMAPPED:
        return "found_unmapped_target"
    if key in approved_alternate_keys:
        return "approved_alternate"
    if mapped_metric_name:
        return "mapped_base_metric"
    return "unknown_unmapped"


def _formula_proposal_prompt_fact_pool(
    fact_pool: tuple[FormulaProposalFact, ...],
) -> list[dict[str, object]]:
    return [
        {
            "taxonomy": row["taxonomy"],
            "concept": row["concept"],
            "label": row["label"],
            "mapping_statuses": row["mapping_statuses"],
            "mapped_metric_names": row["mapped_metric_names"],
            "fact_rows": row["fact_rows"],
            "units": row["units"],
            "period_types": row["period_types"],
            "forms": row["forms"],
            "latest_fiscal_year": row["latest_fiscal_year"],
            "fiscal_periods": row["fiscal_periods"],
            "sample_raw_fact_ids": row["sample_raw_fact_ids"],
        }
        for row in _formula_proposal_fact_pool_summary_rows(fact_pool)
    ]


def _formula_proposal_fact_pool_summary_rows(
    fact_pool: tuple[FormulaProposalFact, ...],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[FormulaProposalFact]] = {}
    for fact in fact_pool:
        grouped.setdefault((fact.taxonomy, fact.concept), []).append(fact)
    rows: list[dict[str, Any]] = []
    for (taxonomy, concept), facts in sorted(grouped.items()):
        rows.append(
            {
                "taxonomy": taxonomy,
                "concept": concept,
                "label": next((fact.label for fact in facts if fact.label), ""),
                "mapping_statuses": _join_values(sorted({fact.mapping_status for fact in facts})),
                "mapped_metric_names": _join_values(sorted({fact.mapped_metric_name for fact in facts if fact.mapped_metric_name})),
                "fact_rows": len(facts),
                "units": _join_values(sorted({fact.unit for fact in facts if fact.unit})),
                "period_types": _join_values(sorted({fact.period_type for fact in facts if fact.period_type})),
                "forms": _join_values(sorted({fact.form for fact in facts if fact.form})),
                "latest_fiscal_year": max((fact.fiscal_year for fact in facts if fact.fiscal_year is not None), default=""),
                "fiscal_periods": _join_values(sorted({fact.fiscal_period for fact in facts if fact.fiscal_period})),
                "sample_raw_fact_ids": _join_values(tuple(fact.raw_fact_id for fact in facts[:5])),
                "sample_accessions": _join_values(tuple(dict.fromkeys(fact.accession_number for fact in facts if fact.accession_number))[:3]),
            }
        )
    return rows


def _formula_proposal_fact_pool_by_key(
    fact_pool: tuple[FormulaProposalFact, ...],
) -> dict[tuple[str, str], list[FormulaProposalFact]]:
    grouped: dict[tuple[str, str], list[FormulaProposalFact]] = {}
    for fact in fact_pool:
        grouped.setdefault(fact.concept_key, []).append(fact)
    return grouped


def _formula_proposal_provider_configs(settings: Settings | None):
    return default_formula_proposal_provider_configs(
        gemini_api_key=_secret_value(getattr(settings, "gemini_api_key", None)),
        openai_api_key=_secret_value(getattr(settings, "openai_api_key", None)),
        gemini_model=str(getattr(settings, "gemini_formula_proposal_model", "") or "gemini-2.5-flash"),
        openai_model=str(getattr(settings, "openai_formula_proposal_model", "") or "gpt-4.1-mini"),
    )


def _formula_proposal_cache_dir(settings: Settings | None) -> Path:
    base_dir = getattr(settings, "knowledge_storage_dir", None) if settings is not None else None
    if base_dir is None:
        base_path = PROJECT_ROOT / "data_store" / "knowledge"
    else:
        base_path = Path(base_dir)
        if not base_path.is_absolute():
            base_path = PROJECT_ROOT / base_path
    return base_path / FORMULA_PROPOSAL_CACHE_SUBDIR


def _secret_value(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        secret = getter()
        return secret.strip() if secret and secret.strip() else None
    text = str(value).strip()
    return text or None


def _formula_proposal_no_context_row(target: FormulaProposalTarget) -> dict[str, Any]:
    return {
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "target_primary_statement": target.statement_type,
        "context_id": "",
        "period_context": "",
        "provider_name": "",
        "model_name": "",
        "provider_status": "not_requested",
        "target_is_zero": "",
        "formula_expression": "",
        "components": "",
        "confidence": "",
        "validation_status": "not_applicable",
        "validation_skip_reason": "no_eligible_period_context",
        "agreement_label": "",
        "cache_status": CACHE_STATUS_UNAVAILABLE,
        "formula_context_hash": "",
        "common_period_units": "",
        "matched_raw_fact_ids": "",
        "matched_accession_numbers": "",
        "invalid_components": "",
        "circular_components": "",
        "reason": "No period-scoped raw fact context was available for this target statement.",
        "uncertainty": "",
        "error": "",
        "cache_warning": "",
        "prompt_version": "",
    }


def _format_formula_period_context(period_context: dict[str, object]) -> str:
    fiscal_year = period_context.get("fiscal_year") or ""
    fiscal_period = period_context.get("fiscal_period") or ""
    period_type = period_context.get("period_type") or ""
    unit = period_context.get("unit") or ""
    start_date = period_context.get("start_date") or ""
    end_date = period_context.get("end_date") or ""
    forms = _join_values(period_context.get("forms") or ())
    accessions = _join_values(period_context.get("accession_numbers") or ())
    date_part = f"{start_date}->{end_date}" if start_date or end_date else ""
    return " | ".join(
        part
        for part in (
            f"{fiscal_year} {fiscal_period}".strip(),
            str(period_type),
            str(unit),
            str(date_part),
            forms,
            accessions,
        )
        if part
    )


def _formula_proposal_diagnostic_rows(
    *,
    target: FormulaProposalTarget,
    context: FormulaProposalContext,
    proposals: tuple[FormulaProposalProviderResult, ...],
    validations: tuple[FormulaProposalValidationResult, ...],
    agreement_label: str,
    formula_context_hashes: tuple[str, ...],
    cache_statuses: tuple[str, ...],
    cache_warnings: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    period_context = _format_formula_period_context(context.period_context)
    for proposal, validation, formula_hash, cache_status, cache_warning in zip(
        proposals,
        validations,
        formula_context_hashes,
        cache_statuses,
        cache_warnings,
        strict=False,
    ):
        rows.append(
            {
                "target_metric_name": target.target_metric_name,
                "target_xbrl_concept": target.target_xbrl_concept,
                "target_primary_statement": context.target_primary_statement,
                "context_id": context.context_id,
                "period_context": period_context,
                "provider_name": proposal.provider_name,
                "model_name": proposal.model_name,
                "provider_status": proposal.provider_status,
                "target_is_zero": _yes_no(proposal.target_is_zero),
                "formula_expression": proposal.formula_expression,
                "components": _formula_component_summary(proposal),
                "concepts_provided": _context_concepts_provided(context),
                "confidence": f"{proposal.confidence:.2f}",
                "validation_status": validation.validation_status,
                "validation_skip_reason": validation.skip_reason,
                "agreement_label": agreement_label,
                "cache_status": cache_status,
                "formula_context_hash": formula_hash[:16],
                "common_period_units": _join_values(validation.common_period_units),
                "matched_raw_fact_ids": _join_values(validation.matched_raw_fact_ids),
                "matched_accession_numbers": _join_values(validation.matched_accession_numbers),
                "invalid_components": _join_values(validation.invalid_components),
                "circular_components": _join_values(validation.circular_components),
                "reason": proposal.reason,
                "uncertainty": proposal.uncertainty,
                "error": proposal.error,
                "cache_warning": cache_warning,
                "prompt_version": proposal.prompt_version,
            }
        )
    return rows


def _context_concepts_provided(context: FormulaProposalContext) -> str:
    concepts = [
        f"{row.get('taxonomy')}:{row.get('concept')}"
        for row in context.prompt_fact_pool
        if row.get("taxonomy") and row.get("concept")
    ]
    return _join_values(tuple(dict.fromkeys(concepts)))


def _formula_proposal_component_rows(
    *,
    target: FormulaProposalTarget,
    context: FormulaProposalContext,
    proposals: tuple[FormulaProposalProviderResult, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fact_pool_by_key = _formula_proposal_fact_pool_by_key(context.facts)
    period_context = _format_formula_period_context(context.period_context)
    for proposal in proposals:
        for component in proposal.components:
            key = (component.taxonomy.strip().lower(), component.concept.strip().lower())
            facts = fact_pool_by_key.get(key, [])
            rows.append(
                {
                    "target_metric_name": target.target_metric_name,
                    "target_xbrl_concept": target.target_xbrl_concept,
                    "target_primary_statement": context.target_primary_statement,
                    "context_id": context.context_id,
                    "period_context": period_context,
                    "provider_name": proposal.provider_name,
                    "component_name": component.component_name,
                    "operator": component.operator,
                    "component_xbrl_concept": f"{component.taxonomy}:{component.concept}",
                    "statement_relationship": context.statement_relationship_by_key.get(key, ""),
                    "mapping_statuses": _join_values(sorted({fact.mapping_status for fact in facts})),
                    "mapped_metric_names": _join_values(sorted({fact.mapped_metric_name for fact in facts if fact.mapped_metric_name})),
                    "mapped_statement_types": _join_values(sorted({fact.mapped_statement_type for fact in facts if fact.mapped_statement_type})),
                    "raw_fact_rows": len(facts),
                    "units": _join_values(sorted({fact.unit for fact in facts if fact.unit})),
                    "period_types": _join_values(sorted({fact.period_type for fact in facts if fact.period_type})),
                    "sample_raw_fact_ids": _join_values(tuple(fact.raw_fact_id for fact in facts[:5])),
                    "role": component.role,
                    "reason": component.reason,
                }
            )
    return rows


def _formula_proposal_summary_rows(
    *,
    targets: tuple[FormulaProposalTarget, ...],
    fact_pool: tuple[FormulaProposalFact, ...],
    diagnostics: list[dict[str, Any]],
    consensus_counts: dict[str, int],
    target_limit: int | None,
    context_count: int,
    available_context_count: int,
    skipped_context_count: int,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    provider_requests = sum(1 for row in diagnostics if row.get("provider_name"))
    proposed = sum(row.get("provider_status") == PROVIDER_STATUS_PROPOSED for row in diagnostics)
    target_zero = sum(row.get("provider_status") == PROVIDER_STATUS_TARGET_ZERO for row in diagnostics)
    no_formula = sum(row.get("provider_status") == PROVIDER_STATUS_NO_FORMULA for row in diagnostics)
    unavailable = sum(row.get("provider_status") == PROVIDER_STATUS_UNAVAILABLE for row in diagnostics)
    failed = sum(row.get("provider_status") == PROVIDER_STATUS_FAILED for row in diagnostics)
    validated = sum(row.get("validation_status") == VALIDATION_STATUS_VALIDATED for row in diagnostics)
    zero_evidence_validated = sum(row.get("validation_status") == VALIDATION_STATUS_ZERO_EVIDENCE for row in diagnostics)
    consensus_validated = consensus_counts.get(CONSENSUS_VALIDATED, 0)
    consensus_target_zero = consensus_counts.get(CONSENSUS_TARGET_ZERO, 0)
    cache_reused = sum(
        row.get("cache_status") in {CACHE_STATUS_REUSED_EXACT_CONTEXT, CACHE_STATUS_REUSED_VALIDATION_FAILED}
        for row in diagnostics
    )
    cache_generated = sum(row.get("cache_status") == CACHE_STATUS_GENERATED_NEW for row in diagnostics)
    cache_unavailable = sum(row.get("cache_status") == CACHE_STATUS_UNAVAILABLE for row in diagnostics)
    cache_invalid = sum(row.get("cache_status") == CACHE_STATUS_ENTRY_INVALID for row in diagnostics)
    limit_note = f"target limit applied: {target_limit}" if target_limit and target_limit > 0 else "all missing targets evaluated"
    return [
        {
            "evidence_item": "formula proposal model panel",
            "value": "run",
            "notes": "Report-only evidence; no recovered metrics were persisted.",
        },
        {
            "evidence_item": "missing targets sent to formula panel",
            "value": len(targets),
            "notes": limit_note,
        },
        {
            "evidence_item": "eligible raw fact pool rows",
            "value": len(fact_pool),
            "notes": "Numeric raw SEC/XBRL facts, including found targets, mapped metrics, alternates, and unknown facts.",
        },
        {
            "evidence_item": "period-scoped formula contexts",
            "value": context_count,
            "notes": (
                "Representative contexts evaluated; "
                f"available={available_context_count}; "
                f"skipped_by_cap={skipped_context_count}; "
                f"cap_per_target={FORMULA_PROPOSAL_CONTEXT_LIMIT_PER_TARGET}."
            ),
        },
        {
            "evidence_item": "provider proposal requests",
            "value": provider_requests,
            "notes": "Configured providers per missing target and representative period context.",
        },
        {
            "evidence_item": "formula proposal cache",
            "value": f"reused={cache_reused}; generated={cache_generated}; unavailable={cache_unavailable}; invalid={cache_invalid}",
            "notes": str(cache_dir),
        },
        {
            "evidence_item": "formula proposals returned",
            "value": proposed,
            "notes": f"target_zero={target_zero}; no_formula={no_formula}; unavailable={unavailable}; failed={failed}",
        },
        {
            "evidence_item": "validated formula proposal rows",
            "value": validated,
            "notes": "Validation checks component membership, circular use, unit/period compatibility, and duplicates.",
        },
        {
            "evidence_item": "zero-target proposal rows",
            "value": target_zero,
            "notes": (
                f"validated_zero_evidence={zero_evidence_validated}; "
                "validation checks cited zero-evidence facts are in the same-period raw fact pool."
            ),
        },
        {
            "evidence_item": "model-consensus validated targets",
            "value": consensus_validated,
            "notes": "At least two providers returned the same validated component signature.",
        },
        {
            "evidence_item": "model-consensus zero-target decisions",
            "value": consensus_target_zero,
            "notes": "At least two providers returned an evidence-backed zero-target decision.",
        },
    ]


def _formula_component_summary(proposal: FormulaProposalProviderResult) -> str:
    return _join_values(
        tuple(
            f"{component.operator} {component.taxonomy}:{component.concept}"
            for component in proposal.components
        )
    )


def _debt_recovery_results(
    connection: sqlite3.Connection,
    *,
    company_id: int | None,
) -> tuple[MetricRecoveryResult, ...]:
    if company_id is None:
        return ()
    return recover_debt_metrics(
        _debt_recovery_source_metrics(connection, company_id),
        candidate_metric_names=(),
    )


def _debt_recovery_source_metrics(
    connection: sqlite3.Connection,
    company_id: int,
) -> tuple[MetricRecoverySource, ...]:
    rows = _fetch_all(
        connection,
        """
        SELECT
            metric_id,
            company_id,
            accession_number,
            raw_fact_id,
            statement_type,
            metric_name,
            value_numeric,
            unit,
            period_type,
            fiscal_year,
            fiscal_period,
            start_date,
            end_date,
            filing_date,
            is_active_window
        FROM financial_metrics
        WHERE company_id = ?
          AND statement_type = 'balance_sheet'
        ORDER BY fiscal_year, fiscal_period, metric_name, accession_number
        """,
        [company_id],
    )
    metrics: list[MetricRecoverySource] = []
    for row in rows:
        value = _parse_decimal_text(str(row.get("value_numeric") or ""))
        if value is None:
            continue
        metrics.append(
            MetricRecoverySource(
                metric_id=row.get("metric_id"),
                company_id=row.get("company_id"),
                accession_number=str(row.get("accession_number") or ""),
                raw_fact_id=row.get("raw_fact_id"),
                statement_type=str(row.get("statement_type") or ""),
                metric_name=str(row.get("metric_name") or ""),
                value_numeric=value,
                unit=str(row.get("unit") or ""),
                period_type=str(row.get("period_type") or ""),
                fiscal_year=row.get("fiscal_year"),
                fiscal_period=row.get("fiscal_period"),
                start_date=_date_from_text(row.get("start_date")),
                end_date=_date_from_text(row.get("end_date")),
                filing_date=_date_from_text(row.get("filing_date")),
                is_active_window=bool(row.get("is_active_window")),
            )
        )
    return tuple(metrics)


def _debt_recovery_formula_catalog_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for formula in DEBT_RECOVERY_FORMULAS:
        required_components = [
            component.component_name
            for component in formula.components
            if component.required
        ]
        optional_zero_components = [
            component.component_name
            for component in formula.components
            if component.zero_if_absent
        ]
        rows.append(
            {
                "target_metric_name": formula.target_metric_name,
                "target_xbrl_concept": formula.target_xbrl_concept,
                "formula_name": formula.formula_name,
                "formula_expression": _debt_formula_expression(formula),
                "required_components": _join_values(required_components),
                "optional_zero_if_absent_components": _join_values(optional_zero_components),
                "component_metric_names_searched": _join_values(
                    _component_metric_search_text(component)
                    for component in formula.components
                ),
            }
        )
    return rows


def _debt_recovery_formula_catalog_text() -> list[str]:
    lines = ["```text"]
    for formula in DEBT_RECOVERY_FORMULAS:
        required_components = [
            component.component_name
            for component in formula.components
            if component.required
        ]
        optional_zero_components = [
            component.component_name
            for component in formula.components
            if component.zero_if_absent
        ]
        lines.extend(
            [
                f"{formula.formula_name}:",
                f"  {_debt_formula_expression(formula)}",
                f"  required components: {_join_values(required_components) or 'none'}",
                (
                    "  optional zero-if-absent components: "
                    f"{_join_values(optional_zero_components) or 'none'}"
                ),
                "",
            ]
        )
    if lines[-1] == "":
        lines.pop()
    lines.append("```")
    return lines


def _debt_formula_expression(formula: Any) -> str:
    terms = [_component_formula_term(component) for component in formula.components]
    return f"{formula.target_metric_name} = {' + '.join(terms)}"


def _component_formula_term(component: Any) -> str:
    metric_names = " or ".join(component.metric_names)
    if component.zero_if_absent:
        return f"{metric_names} (optional zero-if-absent)"
    return metric_names


def _component_metric_search_text(component: Any) -> str:
    return f"{component.component_name}: {' or '.join(component.metric_names)}"


def _debt_recovery_summary_rows(results: tuple[MetricRecoveryResult, ...]) -> list[dict[str, Any]]:
    if not results:
        return [
            {
                "evidence_item": "debt recovery diagnostics",
                "value": "none",
                "notes": "No active mapped debt target or component metrics were available.",
            }
        ]
    recoverable = sum(
        result.target_recovery_status in {TARGET_DIRECT_MAPPED, TARGET_DERIVED_FROM_COMPONENTS}
        for result in results
    )
    incomplete = sum(result.target_recovery_status == TARGET_DECOMPOSITION_INCOMPLETE for result in results)
    ambiguous = sum(
        result.skip_reason in {SKIP_DUPLICATE_COMPONENT_FACTS, SKIP_UNIT_MISMATCH, SKIP_PERIOD_MISMATCH}
        for result in results
    )
    assumed_zero = sum(len(result.assumed_zero_components) for result in results)
    return [
        {
            "evidence_item": "debt recovery targets evaluated",
            "value": len(results),
            "notes": "DebtCurrent and DebtNoncurrent report-only diagnostics across active periods.",
        },
        {
            "evidence_item": "recoverable debt target cases",
            "value": recoverable,
            "notes": "Includes direct mapped targets and component-derived report-only values.",
        },
        {
            "evidence_item": "unrecoverable debt target cases",
            "value": incomplete,
            "notes": "Required component, period, unit, or duplicate gap remains.",
        },
        {
            "evidence_item": "ambiguous debt recovery cases",
            "value": ambiguous,
            "notes": "Duplicate same-period facts, unit mismatch, or period mismatch blocked recovery.",
        },
        {
            "evidence_item": "assumed-zero debt components",
            "value": assumed_zero,
            "notes": "Optional components allowed by formula policy and absent after active-period inspection.",
        },
    ]


def _debt_recovery_result_rows(results: tuple[MetricRecoveryResult, ...]) -> list[dict[str, Any]]:
    return [
        {
            "target_metric_name": result.target_metric_name,
            "target_xbrl_concept": result.target_xbrl_concept,
            "fiscal_year": result.fiscal_year or "",
            "fiscal_period": result.fiscal_period or "",
            "period_type": result.period_type,
            "target_recovery_status": result.target_recovery_status,
            "formula_name": result.formula_name or "",
            "formula_version": result.formula_version,
            "calculated_value": _report_decimal(result.value_numeric),
            "unit": result.unit or "",
            "source_metric_ids": _join_values(result.source_metric_ids),
            "source_raw_fact_ids": _join_values(result.source_raw_fact_ids),
            "source_accession_numbers": _join_values(result.source_accession_numbers),
            "assumed_zero_components": _join_values(result.assumed_zero_components),
            "missing_required_components": _join_values(result.missing_required_components),
            "review_status": result.review_status,
            "skip_reason": result.skip_reason or "",
            "notes": _debt_recovery_note(result),
        }
        for result in results
    ]


def _debt_recovery_component_rows(results: tuple[MetricRecoveryResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for component in result.components:
            policy = DEBT_RECOVERY_COMPONENT_POLICY.get(
                (result.formula_name or "", component.component_name)
            )
            rows.append(
                {
                    "target_metric_name": result.target_metric_name,
                    "fiscal_year": result.fiscal_year or "",
                    "fiscal_period": result.fiscal_period or "",
                    "formula_name": result.formula_name or "",
                    "component_name": component.component_name,
                    "component_required": _yes_no(policy.required) if policy is not None else "",
                    "zero_if_absent": _yes_no(policy.zero_if_absent) if policy is not None else "",
                    "component_availability": _component_availability(component.component_status),
                    "component_status": component.component_status,
                    "candidate_metric_names": _join_values(component.candidate_metric_names),
                    "component_value": _report_decimal(component.value_numeric),
                    "unit": component.unit or "",
                    "source_metric_ids": _join_values(component.source_metric_ids),
                    "source_raw_fact_ids": _join_values(component.source_raw_fact_ids),
                    "source_accession_numbers": _join_values(component.source_accession_numbers),
                    "coverage_proof": _join_values(component.coverage_proof),
                    "skip_reason": component.skip_reason or "",
                    "notes": component.notes,
                }
            )
    return rows


def _component_availability(component_status: str) -> str:
    if component_status == COMPONENT_MAPPED:
        return "found mapped component"
    if component_status == COMPONENT_ASSUMED_ZERO:
        return "not found; optional component assumed zero"
    if component_status == COMPONENT_MISSING_REQUIRED:
        return "not found; required component missing"
    if component_status == COMPONENT_CANDIDATE_REVIEW_REQUIRED:
        return "candidate only; not approved for recovery"
    if component_status == COMPONENT_AMBIGUOUS:
        return "found but ambiguous; not used"
    return component_status


def _debt_recovery_note(result: MetricRecoveryResult) -> str:
    if result.target_recovery_status == TARGET_DIRECT_MAPPED:
        return "Direct mapped base metric; no recovery needed."
    if result.target_recovery_status == TARGET_DERIVED_FROM_COMPONENTS:
        if result.assumed_zero_components:
            return "Report-only recovered value; optional components were assumed zero with coverage proof."
        return "Report-only recovered value from mapped component metrics."
    if result.skip_reason:
        return "Recovery skipped with explicit reason; no recovered value created."
    return ""


def _mapping_profile_reuse_rows(
    *,
    assignment: CompanyIndustryLabelAssignment,
    target_raw_fact_coverage: list[dict[str, Any]],
    approved_learned_mappings: list[dict[str, Any]],
    unknown_xbrl_concepts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize direct mapping and learned-mapping reuse evidence for the report."""
    industry_labels = assignment.assigned_industry_labels
    catalog_mappings = mapping_candidates_by_key(industry_labels)
    missing_targets = [
        row
        for row in target_raw_fact_coverage
        if row.get("status") == STATUS_MISSING_TARGET
    ]
    found_targets = [
        row
        for row in target_raw_fact_coverage
        if row.get("status") in {STATUS_FOUND_MAPPED, STATUS_FOUND_MAPPED_ALTERNATE}
    ]
    found_unmapped = [
        row
        for row in target_raw_fact_coverage
        if row.get("status") == STATUS_FOUND_UNMAPPED
    ]
    missing_metric_names = sorted(
        {
            str(row.get("internal_metric_name"))
            for row in missing_targets
            if row.get("internal_metric_name")
        }
    )
    return [
        {
            "evidence_item": "approved hard industry labels",
            "value": _join(tuple(industry_labels)),
            "evidence_source": assignment.assignment_source or "not available",
            "notes": (
                f"status={assignment.label_status or 'not available'}; "
                f"reason={assignment.assignment_reason or 'not available'}"
            ),
        },
        {
            "evidence_item": "target XBRL concepts selected",
            "value": len(target_raw_fact_coverage),
            "evidence_source": "src/processing/mapping_catalog.py",
            "notes": (
                f"{len(found_targets)} found/mapped; "
                f"{len(found_unmapped)} found_unmapped; "
                f"{len(missing_targets)} missing"
            ),
        },
        {
            "evidence_item": "approved learned mapping reuse",
            "value": _yes_no(bool(approved_learned_mappings)),
            "evidence_source": "xbrl_concept_mappings approved rows",
            "notes": (
                f"{len(approved_learned_mappings)} approved mappings "
                f"({_scope_count_summary(approved_learned_mappings)}); "
                f"{len(catalog_mappings)} source-controlled catalog concepts selected"
            ),
        },
        {
            "evidence_item": "missing target metrics for formula review",
            "value": len(missing_metric_names),
            "evidence_source": "target raw fact coverage",
            "notes": (
                "Missing targets are handled by report-only formula proposal "
                f"diagnostics when enabled: {_join(tuple(missing_metric_names))}"
            ),
        },
        {
            "evidence_item": "mapping expansion review pool",
            "value": len(unknown_xbrl_concepts),
            "evidence_source": "raw_xbrl_facts minus approved/catalog mappings",
            "notes": "unknown concepts remain raw evidence until a mapping is approved",
        },
    ]

def _scope_count_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "none"
    counts: dict[str, int] = {}
    for row in rows:
        scope = str(row.get("scope_type") or "unknown")
        counts[scope] = counts.get(scope, 0) + 1
    return ", ".join(f"{scope}={count}" for scope, count in sorted(counts.items()))


def _target_coverage_status(observed_rows: int, mapped_rows: int) -> str:
    if observed_rows <= 0:
        return STATUS_MISSING_TARGET
    if mapped_rows > 0:
        return STATUS_FOUND_MAPPED
    return STATUS_FOUND_UNMAPPED


def _target_rows_with_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    if status == STATUS_FOUND_MAPPED:
        return [
            row
            for row in rows
            if row.get("status") in {STATUS_FOUND_MAPPED, STATUS_FOUND_MAPPED_ALTERNATE}
        ]
    return [row for row in rows if row.get("status") == status]


def _metric_counts_by_statement(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            statement_type,
            COUNT(*) AS total_metrics,
            SUM(CASE WHEN is_active_window = 1 THEN 1 ELSE 0 END) AS active_metrics
        FROM financial_metrics
        WHERE company_id = ?
        GROUP BY statement_type
        ORDER BY statement_type
        """,
        [company_id],
    )


def _supported_mapping_context(
    connection: sqlite3.Connection,
    company_id: int,
    cik: str,
) -> tuple[dict[tuple[str, str], Any], list[dict[str, Any]], set[tuple[str, str]]]:
    industry_labels = tuple(
        str(row["industry_label"])
        for row in _fetch_all(
            connection,
            """
            SELECT industry_label
            FROM company_industry_labels
            WHERE company_id = ? AND status = 'approved'
            """,
            [company_id],
        )
    )
    catalog_mappings = mapping_candidates_by_key(industry_labels)
    approved_mapping_rows = _learned_mapping_rows(connection, cik, status="approved")
    approved_keys = {
        (str(row["taxonomy"]), str(row["observed_raw_concept"]))
        for row in approved_mapping_rows
    }
    supported_keys = set(catalog_mappings) | approved_keys
    return catalog_mappings, approved_mapping_rows, supported_keys


def _raw_fact_mapping_coverage(
    connection: sqlite3.Connection,
    company_id: int | None,
    cik: str | None,
) -> list[dict[str, Any]]:
    if company_id is None or not cik:
        return []
    catalog_mappings, approved_mapping_rows, supported_keys = _supported_mapping_context(
        connection,
        company_id,
        cik,
    )
    raw_groups = _fetch_all(
        connection,
        """
        SELECT
            taxonomy,
            concept,
            COUNT(*) AS raw_fact_rows
        FROM raw_xbrl_facts
        WHERE cik = ?
        GROUP BY taxonomy, concept
        """,
        [cik],
    )
    mapped_summary = _fetch_one(
        connection,
        """
        SELECT
            COUNT(*) AS financial_metric_rows,
            COUNT(DISTINCT m.raw_fact_id) AS mapped_raw_facts,
            COUNT(DISTINCT f.concept) AS mapped_raw_concepts
        FROM financial_metrics AS m
        LEFT JOIN raw_xbrl_facts AS f
            ON f.id = m.raw_fact_id
        WHERE m.company_id = ?
        """,
        [company_id],
    )
    raw_fact_rows = sum(int(row["raw_fact_rows"] or 0) for row in raw_groups)
    distinct_raw_concepts = len(raw_groups)
    raw_facts_with_supported_concepts = sum(
        int(row["raw_fact_rows"] or 0)
        for row in raw_groups
        if (str(row["taxonomy"]), str(row["concept"])) in supported_keys
    )
    unknown_raw_fact_rows = raw_fact_rows - raw_facts_with_supported_concepts
    unknown_raw_concepts = sum(
        1
        for row in raw_groups
        if (str(row["taxonomy"]), str(row["concept"])) not in supported_keys
    )
    financial_metric_rows = int(mapped_summary.get("financial_metric_rows") or 0)
    mapped_raw_facts = int(mapped_summary.get("mapped_raw_facts") or 0)
    mapped_raw_concepts = int(mapped_summary.get("mapped_raw_concepts") or 0)
    supported_but_not_mapped = max(raw_facts_with_supported_concepts - mapped_raw_facts, 0)
    return [
        {
            "coverage_item": "raw XBRL facts downloaded/stored for ticker",
            "count": raw_fact_rows,
            "note": "normalized SEC companyfacts plus Inline XBRL extension archive",
        },
        {
            "coverage_item": "raw facts mapped into financial_metrics",
            "count": mapped_raw_facts,
            "note": _coverage_note(mapped_raw_facts, raw_fact_rows),
        },
        {
            "coverage_item": "financial_metrics rows created",
            "count": financial_metric_rows,
            "note": "curated base metrics available to calculations",
        },
        {
            "coverage_item": "raw facts not mapped into financial_metrics",
            "count": raw_fact_rows - mapped_raw_facts,
            "note": "unknown concepts or unusable supported facts",
        },
        {
            "coverage_item": "raw facts with supported concept names",
            "count": raw_facts_with_supported_concepts,
            "note": "concept exists in the approved mapping catalog",
        },
        {
            "coverage_item": "supported-concept raw facts skipped",
            "count": supported_but_not_mapped,
            "note": "usually quality flags, missing values, or duplicate/ambiguous facts",
        },
        {
            "coverage_item": "unknown raw fact rows",
            "count": unknown_raw_fact_rows,
            "note": "concept not in current base metric mapping",
        },
        {
            "coverage_item": "distinct raw XBRL concepts observed",
            "count": distinct_raw_concepts,
            "note": "all raw concepts stored for this ticker",
        },
        {
            "coverage_item": "distinct mapped raw concepts",
            "count": mapped_raw_concepts,
            "note": "observed raw concepts that became financial_metrics",
        },
        {
            "coverage_item": "distinct unknown raw concepts",
            "count": unknown_raw_concepts,
            "note": "candidate tags to review for future mapping",
        },
        {
            "coverage_item": "supported SEC/XBRL tags in mapping catalog",
            "count": len(supported_keys),
            "note": (
                f"maps into {len({mapping.metric_name for mapping in catalog_mappings.values()} | {str(row['metric_name']) for row in approved_mapping_rows})} "
                "business metrics"
            ),
        },
    ]


def _alternate_xbrl_tags(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    observed_rows = _fetch_all(
        connection,
        """
        SELECT
            m.statement_type,
            m.metric_name,
            f.concept,
            COUNT(*) AS mapped_rows,
            SUM(CASE WHEN m.is_active_window = 1 THEN 1 ELSE 0 END) AS active_rows
        FROM financial_metrics AS m
        LEFT JOIN raw_xbrl_facts AS f
            ON f.id = m.raw_fact_id
        WHERE m.company_id = ? AND f.concept IS NOT NULL
        GROUP BY m.statement_type, m.metric_name, f.concept
        ORDER BY m.statement_type, m.metric_name, f.concept
        """,
        [company_id],
    )
    observed_by_metric: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in observed_rows:
        key = (str(row["statement_type"]), str(row["metric_name"]))
        observed_by_metric.setdefault(key, []).append(row)

    supported_by_metric: dict[tuple[str, str], list[str]] = {}
    for concept, mapping in BASE_METRIC_MAPPINGS.items():
        key = (mapping.statement_type, mapping.metric_name)
        supported_by_metric.setdefault(key, []).append(concept)
    company = _fetch_one(
        connection,
        "SELECT cik FROM companies WHERE company_id = ?",
        [company_id],
    )
    for row in _learned_mapping_rows(
        connection,
        company.get("cik"),
        status="approved",
    ):
        key = (str(row["statement_type"]), str(row["metric_name"]))
        tag = f"{row['taxonomy']}:{row['observed_raw_concept']}"
        if tag not in supported_by_metric.setdefault(key, []):
            supported_by_metric[key].append(tag)

    rows = []
    for key, supported_tags in sorted(supported_by_metric.items()):
        observed = observed_by_metric.get(key, [])
        if len(supported_tags) <= 1 and len(observed) <= 1:
            continue
        rows.append(
            {
                "metric_name": key[1],
                "statement_type": key[0],
                "supported_sec_xbrl_tags": _join(sorted(supported_tags)),
                "observed_tags": _join(
                    f"{row['concept']} ({row['mapped_rows']} rows)" for row in observed
                ),
                "mapped_rows": sum(int(row["mapped_rows"] or 0) for row in observed),
                "active_rows": sum(int(row["active_rows"] or 0) for row in observed),
            }
        )
    return rows


def _unknown_xbrl_concepts(
    connection: sqlite3.Connection,
    company_id: int | None,
    cik: str | None,
) -> list[dict[str, Any]]:
    if company_id is None or not cik:
        return []
    _, _, supported_keys = _supported_mapping_context(connection, company_id, cik)
    rows = _fetch_all(
        connection,
        """
        SELECT
            concept AS raw_xbrl_concept,
            COALESCE(MAX(label), '') AS label,
            taxonomy,
            COUNT(*) AS raw_fact_rows,
            COUNT(DISTINCT unit) AS unit_count,
            COALESCE(GROUP_CONCAT(DISTINCT form), '') AS forms,
            MAX(end_date) AS latest_end_date,
            MAX(filed_date) AS latest_filed_date
        FROM raw_xbrl_facts AS f
        WHERE f.cik = ?
        GROUP BY f.taxonomy, f.concept
        ORDER BY raw_fact_rows DESC, raw_xbrl_concept
        """,
        [cik],
    )
    return [
        row
        for row in rows
        if (str(row["taxonomy"]), str(row["raw_xbrl_concept"])) not in supported_keys
    ]


def _inline_xbrl_coverage(
    connection: sqlite3.Connection,
    cik: str | None,
) -> list[dict[str, Any]]:
    if not cik:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            taxonomy,
            COALESCE(namespace_uri, '') AS namespace_uri,
            COUNT(*) AS raw_fact_rows,
            COUNT(DISTINCT concept) AS concept_count,
            SUM(CASE WHEN is_consolidated = 1 THEN 1 ELSE 0 END) AS consolidated_rows,
            SUM(CASE WHEN is_consolidated = 0 THEN 1 ELSE 0 END) AS dimensional_rows,
            COALESCE(GROUP_CONCAT(DISTINCT form), '') AS forms
        FROM raw_xbrl_facts
        WHERE cik = ? AND source = 'sec_inline_xbrl'
        GROUP BY taxonomy, namespace_uri
        ORDER BY raw_fact_rows DESC, taxonomy
        """,
        [cik],
    )


def _learned_mapping_rows(
    connection: sqlite3.Connection,
    cik: str | None,
    *,
    status: str,
) -> list[dict[str, Any]]:
    if not cik:
        return []
    rows = _fetch_all(
        connection,
        """
        SELECT
            mapping_id,
            metric_name,
            statement_type,
            taxonomy,
            concept AS observed_raw_concept,
            ROUND(confidence, 4) AS confidence,
            scope_type,
            scope_value,
            status,
            match_method,
            COALESCE(evidence_json, '{}') AS evidence_json,
            COALESCE(reviewed_by, '') AS reviewed_by,
            COALESCE(reviewed_at, '') AS reviewed_at
        FROM xbrl_concept_mappings
        WHERE status = ?
          AND (
              scope_type = 'global'
              OR (scope_type = 'company' AND scope_value = ?)
              OR (
                  scope_type = 'industry'
                  AND scope_value IN (
                      SELECT labels.industry_label
                      FROM company_industry_labels AS labels
                      INNER JOIN companies AS company
                          ON company.company_id = labels.company_id
                      WHERE company.cik = ? AND labels.status = 'approved'
                  )
              )
          )
        ORDER BY metric_name, confidence DESC, taxonomy, concept
        """,
        [status, cik, cik],
    )
    rendered_rows: list[dict[str, Any]] = []
    for row in rows:
        row.pop("evidence_json", "{}")
        rendered_rows.append(
            {
                **row,
                "observed_xbrl_concept": (
                    f"{row['taxonomy']}:{row['observed_raw_concept']}"
                    if row.get("taxonomy") and row.get("observed_raw_concept")
                    else ""
                ),
            }
        )
    return rendered_rows


def _coverage_note(mapped_count: int, total_count: int) -> str:
    if total_count <= 0:
        return "0.0% of raw facts"
    return f"{(mapped_count / total_count) * 100:.1f}% of raw facts"


def _metric_lineage_summary(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    rows = _fetch_all(
        connection,
        """
        SELECT
            m.statement_type,
            m.metric_name,
            m.fiscal_year,
            m.fiscal_period,
            m.accession_number,
            m.is_active_window,
            f.concept AS raw_concept
        FROM financial_metrics AS m
        LEFT JOIN raw_xbrl_facts AS f
            ON f.id = m.raw_fact_id
        WHERE m.company_id = ?
        ORDER BY m.statement_type, m.metric_name, m.fiscal_year DESC, m.fiscal_period DESC
        """,
        [company_id],
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["statement_type"]), str(row["metric_name"]))
        entry = grouped.setdefault(
            key,
            {
                "statement_type": key[0],
                "metric_name": key[1],
                "raw_concepts": set(),
                "source_accessions": set(),
                "total_rows": 0,
                "active_rows": 0,
                "inactive_context_rows": 0,
                "active_annual_periods": set(),
                "active_quarterly_periods": set(),
            },
        )
        entry["total_rows"] += 1
        if row.get("raw_concept"):
            entry["raw_concepts"].add(str(row["raw_concept"]))
        if row.get("accession_number"):
            entry["source_accessions"].add(str(row["accession_number"]))
        fiscal_year = row.get("fiscal_year")
        fiscal_period = row.get("fiscal_period")
        if row.get("is_active_window"):
            entry["active_rows"] += 1
            if fiscal_year is not None and fiscal_period:
                period_key = (fiscal_year, str(fiscal_period))
                if str(fiscal_period).upper() == "FY":
                    entry["active_annual_periods"].add(period_key)
                else:
                    entry["active_quarterly_periods"].add(period_key)
        else:
            entry["inactive_context_rows"] += 1

    summary = []
    for entry in grouped.values():
        raw_concepts = sorted(entry["raw_concepts"])
        summary.append(
            {
                "statement_type": entry["statement_type"],
                "metric_name": entry["metric_name"],
                "raw_xbrl_concepts": ", ".join(raw_concepts) if raw_concepts else "not linked",
                "system_mapping": f"{', '.join(raw_concepts) if raw_concepts else 'not linked'} -> {entry['metric_name']}",
                "financial_metric_rows": entry["total_rows"],
                "active_rows": entry["active_rows"],
                "inactive_context_rows": entry["inactive_context_rows"],
                "active_annual_periods": len(entry["active_annual_periods"]),
                "active_quarterly_periods": len(entry["active_quarterly_periods"]),
                "source_accessions": len(entry["source_accessions"]),
            }
        )
    return sorted(summary, key=lambda row: (row["statement_type"], row["metric_name"]))


def _metric_sample(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            metric_id,
            statement_type,
            metric_name,
            fiscal_year,
            fiscal_period,
            value_numeric,
            unit,
            accession_number,
            raw_fact_id,
            is_active_window
        FROM financial_metrics
        WHERE company_id = ?
        ORDER BY statement_type, metric_name, fiscal_year DESC, fiscal_period DESC
        LIMIT 8
        """,
        [company_id],
    )


def _traceability_sample(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            m.metric_id,
            m.statement_type,
            m.metric_name,
            m.fiscal_year,
            m.fiscal_period,
            m.accession_number,
            m.raw_fact_id,
            f.concept AS raw_concept,
            f.unit AS raw_unit,
            f.quality_flags AS raw_quality_flags,
            fi.form_type,
            fi.filing_date
        FROM financial_metrics AS m
        LEFT JOIN raw_xbrl_facts AS f
            ON f.id = m.raw_fact_id
        LEFT JOIN filings AS fi
            ON fi.filing_id = m.filing_id
        WHERE m.company_id = ?
        ORDER BY m.statement_type, m.metric_name, m.fiscal_year DESC, m.fiscal_period DESC
        LIMIT 8
        """,
        [company_id],
    )


def _quality_flags(connection: sqlite3.Connection, cik: str | None) -> tuple[str, ...]:
    if not cik:
        return ()
    rows = _fetch_all(
        connection,
        "SELECT quality_flags FROM raw_xbrl_facts WHERE cik = ?",
        [cik],
    )
    flags: set[str] = set()
    for row in rows:
        value = str(row["quality_flags"]).strip()
        if not value or value == "[]":
            continue
        for flag in value.strip("[]").replace('"', "").split(","):
            clean = flag.strip()
            if clean:
                flags.add(clean)
    return tuple(sorted(flags))


def _write_report(run: ExperimentRun, *, full_report: bool) -> None:
    run.paths.report.parent.mkdir(parents=True, exist_ok=True)
    run.paths.report.write_text(format_saved_report(run, full_report=full_report), encoding="utf-8")


def format_saved_report(run: ExperimentRun, *, full_report: bool = False) -> str:
    """Render the saved Plan 2.5 target mapping report."""
    formula_annotations: dict[str, str] = {}
    formula_rows_by_form = {
        form_type: _proposed_formula_rows_for_missing_targets(
            run.session_after_snapshot,
            form_type=form_type,
            formula_annotations=formula_annotations,
        )
        for form_type in FORMS
    }
    lines = [
        "# Plan 2.5 Target Mapping Report",
        "",
        "## 0. Compact Summary",
        "",
    ]
    lines.extend(_markdown_table(_saved_compact_summary_rows(run, full_report=full_report, formula_rows_by_form=formula_rows_by_form)))
    lines.extend(["", "## 0A. XBRL Concepts Provided By Period", ""])
    lines.extend(["", "### # of concepts provided from XBRL - 10-K", ""])
    lines.extend(_markdown_table(_xbrl_concepts_provided_10k_rows(run.session_after_snapshot)))
    lines.extend(["", "### # of concepts provided from XBRL - 10-Q", ""])
    lines.extend(_markdown_table(_xbrl_concepts_provided_10q_rows(run.session_after_snapshot)))
    lines.extend(
        [
            "",
            "Boundary: formulas and zero-target decisions are review evidence only. They do not populate `financial_metrics` or feed indicators without approval.",
        ]
    )
    if run.error:
        lines.extend(["", "Execution Warning:", run.error])
    if run.warnings:
        lines.extend(["", "Source And Export Warnings:"])
        lines.extend(f"- {warning}" for warning in run.warnings)
    lines.extend(["", "## 1. Target Metrics Mapping Status", ""])
    lines.extend(_markdown_table(_target_metric_status_rows(run.session_after_snapshot)))
    lines.extend(["", "## 2. Proposed Formulas For Formula Recommendations", ""])
    for form_type in FORMS:
        lines.extend(["", f"### {form_type}", ""])
        lines.extend(_markdown_table(formula_rows_by_form[form_type]))
        lines.extend(_formula_annotation_lines_for_rows(formula_rows_by_form[form_type], formula_annotations))
    return "\n".join(lines)


def _saved_compact_summary_rows(
    run: ExperimentRun,
    *,
    full_report: bool,
    formula_rows_by_form: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    snapshot = run.session_after_snapshot
    company = snapshot.get("company") or run.setup_snapshot.get("company") or {}
    before_company = run.session_before_snapshot.get("company") or {}
    target_status_rows = _target_metric_status_rows(snapshot)
    formula_summary = _summary_rows_by_item(snapshot.get("formula_proposal_summary") or [])
    diagnostics = snapshot.get("formula_proposal_diagnostics") or []
    formula_panel = formula_summary.get("formula proposal model panel", {})
    report_output = "saved Plan 2.5 target mapping report"
    if full_report:
        report_output = "saved Plan 2.5 target mapping report; --full-report kept for CLI compatibility"
    return [
        {"Item": "Ticker", "Value": run.ticker},
        {"Item": "CIK", "Value": company.get("cik") or "not available"},
        {"Item": "Run timestamp", "Value": run.run_timestamp},
        {"Item": "Report output", "Value": report_output},
        {"Item": "Company in system", "Value": _yes_no(run.session_decision.company_exists)},
        {
            "Item": "Update check needed this session",
            "Value": _yes_no(_update_check_needed(run.session_decision)) if run.session_decision.company_exists else "not applicable",
        },
        {
            "Item": "10-K check due",
            "Value": (
                "not applicable"
                if not run.session_decision.company_exists
                else f"{_yes_no_unknown(run.session_decision.refresh_due_10k)} "
                f"(next check date before session: {before_company.get('next_check_date_10k') or 'not available'})"
            ),
        },
        {
            "Item": "10-Q check due",
            "Value": (
                "not applicable"
                if not run.session_decision.company_exists
                else f"{_yes_no_unknown(run.session_decision.refresh_due_10q)} "
                f"(next check date before session: {before_company.get('next_check_date_10q') or 'not available'})"
            ),
        },
        {"Item": "SEC update check performed", "Value": _yes_no(run.session_decision.sec_checked)},
        {"Item": "SEC result", "Value": _status_summary(run.session_decision)},
        {"Item": "New filings ingested this session", "Value": _new_filing_summary(run.session_decision.new_filings)},
        {"Item": "Target metrics checked", "Value": len(target_status_rows)},
        {"Item": "Mapped target metrics", "Value": _count_rows_with_value(target_status_rows, "Mapping status", "mapped")},
        {"Item": "Missing target metrics", "Value": _count_rows_with_value(target_status_rows, "Mapping status", "missing")},
        {"Item": "10-K proposed formula rows listed", "Value": len(formula_rows_by_form["10-K"])},
        {"Item": "10-Q proposed formula rows listed", "Value": len(formula_rows_by_form["10-Q"])},
        {
            "Item": "Formula diagnostics run",
            "Value": _yes_no(str(formula_panel.get("value") or "") == "run"),
        },
        {"Item": "Formula proposal contexts", "Value": len({row.get("context_id") for row in diagnostics if row.get("context_id")})},
        {
            "Item": "Formula proposals returned",
            "Value": sum(row.get("provider_status") == PROVIDER_STATUS_PROPOSED for row in diagnostics),
        },
        {
            "Item": "Zero-target evidence rows",
            "Value": sum(row.get("provider_status") == PROVIDER_STATUS_TARGET_ZERO for row in diagnostics),
        },
        {"Item": "Recovered rows inserted into `financial_metrics`", "Value": 0},
        {"Item": "Used by indicators", "Value": "No"},
    ]


def _target_metric_status_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshot.get("target_raw_fact_coverage") or []:
        metric = str(row.get("internal_metric_name") or "")
        statement = str(row.get("statement_type") or "")
        if not metric:
            continue
        entry = grouped.setdefault(
            (metric, statement),
            {
                "statuses": set(),
                "mapped_targets": set(),
                "approved_alternates": set(),
                "target_concepts": set(),
                "required_for_core": False,
                "required_for_specialized_indicators": False,
            },
        )
        status = str(row.get("status") or "")
        if status:
            entry["statuses"].add(status)
        target_concept = str(row.get("target_xbrl_concept") or "")
        if target_concept:
            entry["target_concepts"].add(target_concept)
        if status == STATUS_FOUND_MAPPED and target_concept:
            entry["mapped_targets"].add(target_concept)
        if str(row.get("alternate_mapped_concepts") or ""):
            entry["approved_alternates"].add(str(row.get("alternate_mapped_concepts")))
        entry["required_for_core"] = entry["required_for_core"] or row.get("required_for_core") == "yes"
        entry["required_for_specialized_indicators"] = (
            entry["required_for_specialized_indicators"]
            or row.get("required_for_specialized_indicators") == "yes"
        )

    rows: list[dict[str, Any]] = []
    for (metric, statement), entry in grouped.items():
        statuses = entry["statuses"]
        rows.append(
            {
                "Metric type": _target_metric_type(entry),
                "Metric": metric,
                "Statement": statement,
                "Mapping status": _target_metric_mapping_status(statuses),
                "Mapped target concepts": _join_sorted_values(entry["mapped_targets"]) or "none",
                "Coverage detail": _target_metric_coverage_detail(statuses),
                "Approved alternates": _join_sorted_values(entry["approved_alternates"]) or "none",
                "Target XBRL concepts checked": _join_sorted_values(entry["target_concepts"]) or "none",
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("Metric type") or ""),
            str(item.get("Metric") or ""),
            str(item.get("Statement") or ""),
        ),
    )


def _target_metric_type(entry: dict[str, Any]) -> str:
    if entry.get("required_for_core"):
        return "core"
    if entry.get("required_for_specialized_indicators"):
        return "specialized"
    return "supporting"


def _target_metric_mapping_status(statuses: set[str]) -> str:
    if STATUS_FOUND_MAPPED in statuses or STATUS_FOUND_MAPPED_ALTERNATE in statuses:
        return "mapped"
    if STATUS_FOUND_UNMAPPED in statuses:
        return "found_unmapped"
    if STATUS_MISSING_TARGET in statuses:
        return "missing"
    return "unknown"


def _target_metric_coverage_detail(statuses: set[str]) -> str:
    ordered = [
        status
        for status in (
            STATUS_FOUND_MAPPED,
            STATUS_FOUND_MAPPED_ALTERNATE,
            STATUS_FOUND_UNMAPPED,
            STATUS_MISSING_TARGET,
        )
        if status in statuses
    ]
    return _join_values(ordered) or "unknown"


def _proposed_formula_rows_for_missing_targets(
    snapshot: dict[str, Any],
    *,
    form_type: str,
    formula_annotations: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    missing_metrics = _missing_target_metric_names(snapshot)
    recommendations_by_period: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in snapshot.get("formula_proposal_diagnostics") or []:
        metric = str(row.get("target_metric_name") or "")
        if metric not in missing_metrics:
            continue
        if not _diagnostic_row_matches_form(row, form_type):
            continue
        formula = str(row.get("formula_expression") or "").strip()
        if not formula and row.get("provider_status") != PROVIDER_STATUS_TARGET_ZERO:
            continue
        if row.get("provider_status") not in {PROVIDER_STATUS_PROPOSED, PROVIDER_STATUS_TARGET_ZERO}:
            continue
        components = _strip_concept_prefixes(row.get("components") or "")
        period_labels = _formula_period_labels_for_report(
            row.get("period_context"),
            form_type=form_type,
        )
        if not period_labels:
            period_labels = (_formula_period_context_for_report(row.get("period_context"), form_type=form_type),)
        recommendation = {
            "provider": _provider_label(row),
            "formula": _formula_expression_for_report(metric=metric, row=row, components=components),
            "components": components,
            "validation_status": str(row.get("validation_status") or ""),
            "validation_reason": str(row.get("validation_skip_reason") or ""),
            "confidence": str(row.get("confidence") or ""),
            "reason": str(row.get("reason") or ""),
        }
        statement = str(row.get("target_primary_statement") or "")
        for period_label in period_labels:
            if period_label:
                recommendations_by_period.setdefault((metric, statement, period_label), []).append(recommendation)

    rows: list[dict[str, Any]] = []
    disagreement_grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    grouped: dict[tuple[str, str, tuple[tuple[str, str, str], ...]], dict[str, Any]] = {}
    for (metric, statement, period_label), recommendations in recommendations_by_period.items():
        sorted_recommendations = _sorted_formula_recommendations(recommendations)
        recommendation_formulas = {
            (
                recommendation["formula"],
                recommendation["components"],
            )
            for recommendation in sorted_recommendations
        }
        if len(recommendation_formulas) > 1:
            for recommendation in sorted_recommendations:
                key = (
                    metric,
                    statement,
                    recommendation["provider"],
                    recommendation["formula"],
                    recommendation["components"],
                )
                if key not in disagreement_grouped:
                    disagreement_grouped[key] = {
                        "metric": metric,
                        "statement": statement,
                        "period_labels": [],
                        "recommendations": [],
                    }
                disagreement_grouped[key]["period_labels"].append(period_label)
                disagreement_grouped[key]["recommendations"].append(recommendation)
            continue
        recommendation_signature = tuple(
            (
                recommendation["provider"],
                recommendation["formula"],
                recommendation["components"],
            )
            for recommendation in sorted_recommendations
        )
        key = (metric, statement, recommendation_signature)
        if key not in grouped:
            grouped[key] = {
                "metric": metric,
                "statement": statement,
                "period_labels": [],
                "recommendations": sorted_recommendations,
            }
        grouped[key]["period_labels"].append(period_label)

    rows.extend(
        _formula_report_row_from_period_group(
            group,
            form_type=form_type,
            formula_annotations=formula_annotations,
        )
        for group in disagreement_grouped.values()
    )
    rows.extend(
        _formula_report_row_from_period_group(
            group,
            form_type=form_type,
            formula_annotations=formula_annotations,
        )
        for group in grouped.values()
    )
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("Metric") or ""),
            str(row.get("Statement") or ""),
            -_first_formula_period_sort_value(str(row.get("Period context") or ""), form_type=form_type),
            str(row.get("Providers") or ""),
            str(row.get("Formula") or ""),
        ),
    )


def _formula_report_row_from_period_group(
    group: dict[str, Any],
    *,
    form_type: str,
    formula_annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    recommendations = group["recommendations"]
    return {
        "Metric": group["metric"],
        "Statement": group["statement"],
        "Period context": _format_formula_period_labels_for_report(
            group["period_labels"],
            form_type=form_type,
        ),
        "Providers": _join_unique_texts(recommendation["provider"] for recommendation in recommendations),
        "Formula": _format_formula_recommendation_field(
            recommendations,
            "formula",
            formula_annotations=formula_annotations,
        ),
        "Validation status": _join_unique_texts(
            recommendation["validation_status"] for recommendation in recommendations
        ),
        "Validation reason": _join_unique_texts(
            recommendation["validation_reason"] for recommendation in recommendations
        ),
        "Confidence": _join_unique_texts(recommendation["confidence"] for recommendation in recommendations),
        "Reason": _join_unique_texts(recommendation["reason"] for recommendation in recommendations),
    }


def _format_formula_recommendation_field(
    recommendations: Sequence[dict[str, str]],
    field: str,
    *,
    formula_annotations: dict[str, str] | None = None,
) -> str:
    values = tuple(dict.fromkeys(recommendation.get(field, "") for recommendation in recommendations if recommendation.get(field)))
    if len(values) <= 1:
        if not values:
            return ""
        if field == "formula":
            return _formula_text_for_table(values[0], formula_annotations=formula_annotations)
        return values[0]
    return _join_unique_texts(
        f"{recommendation['provider']}: "
        f"{_formula_text_for_table(recommendation[field], formula_annotations=formula_annotations)}"
        for recommendation in recommendations
        if recommendation.get(field)
    )


def _formula_text_for_table(
    formula: str,
    *,
    formula_annotations: dict[str, str] | None,
) -> str:
    if formula_annotations is None or not _should_annotate_formula(formula):
        return formula
    return _formula_annotation_for_text(formula, formula_annotations)


def _should_annotate_formula(formula: str) -> bool:
    sanitized = _sanitize_markdown_cell_text(formula)
    return len(sanitized) > MARKDOWN_CELL_MAX_CHARS


def _formula_annotation_for_text(formula: str, formula_annotations: dict[str, str]) -> str:
    if formula not in formula_annotations:
        formula_annotations[formula] = f"[F{len(formula_annotations) + 1}]"
    return formula_annotations[formula]


def _formula_annotation_lines_for_rows(
    rows: list[dict[str, Any]],
    formula_annotations: dict[str, str],
) -> list[str]:
    if not rows or not formula_annotations:
        return []
    referenced_labels = {
        label
        for row in rows
        for label in formula_annotations.values()
        if label in str(row.get("Formula") or "")
    }
    if not referenced_labels:
        return []
    formulas_by_label = {label: formula for formula, label in formula_annotations.items()}
    lines = ["", "Formula annotations:"]
    for label in sorted(referenced_labels, key=_formula_annotation_sort_key):
        lines.append(f"- {label} {formulas_by_label[label]}")
    return lines


def _formula_annotation_sort_key(label: str) -> int:
    match = re.fullmatch(r"\[F(\d+)\]", label)
    if not match:
        return 0
    return int(match.group(1))


def _sorted_formula_recommendations(recommendations: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for recommendation in recommendations:
        key = (
            recommendation.get("provider", ""),
            recommendation.get("formula", ""),
            recommendation.get("components", ""),
            recommendation.get("validation_status", ""),
            recommendation.get("validation_reason", ""),
            recommendation.get("confidence", ""),
            recommendation.get("reason", ""),
        )
        unique.setdefault(key, dict(recommendation))
    return sorted(
        unique.values(),
        key=lambda recommendation: (
            recommendation.get("provider", ""),
            recommendation.get("formula", ""),
            recommendation.get("components", ""),
        ),
    )


def _xbrl_concepts_provided_10k_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    counts_by_period = _xbrl_concept_counts_for_report(snapshot)
    annual = counts_by_period.get("10-K", {})
    rows: list[dict[str, Any]] = []
    for year in sorted(_year_labels_from_concept_periods(annual)):
        rows.append(
            {
                "Year": str(year),
                "# of concepts provided": annual.get(str(year), ""),
            }
        )
    return rows


def _xbrl_concepts_provided_10q_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    counts_by_period = _xbrl_concept_counts_for_report(snapshot)
    quarterly = counts_by_period.get("10-Q", {})
    years = sorted(
        {
            year
            for period_label in quarterly
            for year, _quarter in _quarter_labels_from_context(period_label)
        }
    )
    quarter_columns = _quarter_columns_for_concept_counts(quarterly)
    rows: list[dict[str, Any]] = []
    for year in years:
        row: dict[str, Any] = {"Year": str(year)}
        for quarter in quarter_columns:
            row[f"Q{quarter}"] = quarterly.get(_format_quarter_label((year, quarter)), "")
        rows.append(row)
    return rows


def _xbrl_concept_counts_for_report(snapshot: dict[str, Any]) -> dict[str, dict[str, int]]:
    counts_by_period: dict[str, dict[str, int]] = {
        form_type: {}
        for form_type in FORMS
    }
    for row in snapshot.get("xbrl_concept_counts_by_period") or []:
        form_type = _normal_report_form(row.get("form_type"))
        fiscal_year = row.get("fiscal_year")
        fiscal_period = str(row.get("fiscal_period") or "").strip().upper()
        concept_count = _int_or_none(row.get("concept_count"))
        if form_type not in FORMS or fiscal_year is None or concept_count is None:
            continue
        try:
            year = int(fiscal_year)
        except (TypeError, ValueError):
            continue
        if form_type == "10-K":
            counts_by_period[form_type][str(year)] = concept_count
            continue
        quarter = _quarter_number_from_period(fiscal_period)
        if quarter is None:
            continue
        counts_by_period[form_type][_format_quarter_label((year, quarter))] = concept_count
    return counts_by_period


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _quarter_number_from_period(value: str) -> int | None:
    match = re.fullmatch(r"Q([1-4])", str(value or "").strip().upper())
    return int(match.group(1)) if match else None


def _year_labels_from_concept_periods(periods: dict[str, Any]) -> list[int]:
    return [
        int(match.group(1))
        for period_label in periods
        for match in re.finditer(r"\b((?:19|20)\d{2})\b", period_label)
    ]


def _quarter_columns_for_concept_counts(periods: dict[str, Any]) -> list[int]:
    observed = sorted(
        {
            quarter
            for period_label in periods
            for _year, quarter in _quarter_labels_from_context(period_label)
        }
    )
    if not observed:
        return [1, 2, 3]
    observed_set = set(observed)
    return [quarter for quarter in (1, 2, 3, 4) if quarter in observed_set or quarter <= 3]


def _missing_target_metric_names(snapshot: dict[str, Any]) -> set[str]:
    return {
        str(row.get("Metric") or "")
        for row in _target_metric_status_rows(snapshot)
        if row.get("Mapping status") == "missing"
    }


def _diagnostic_row_matches_form(row: dict[str, Any], form_type: str) -> bool:
    context = str(row.get("period_context") or "").upper()
    normalized_form = _normal_report_form(form_type)
    if normalized_form in context:
        return True
    fiscal_period = context.split("|", 1)[0].upper()
    if normalized_form == "10-K":
        return " FY" in f" {fiscal_period} "
    if normalized_form == "10-Q":
        return any(f" Q{quarter}" in f" {fiscal_period} " for quarter in range(1, 5))
    return False


def _normal_report_form(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"10-K", "10-K/A"}:
        return "10-K"
    if text in {"10-Q", "10-Q/A"}:
        return "10-Q"
    return ""


def _formula_period_labels_for_report(value: Any, *, form_type: str) -> tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    normalized_form = _normal_report_form(form_type)
    if normalized_form == "10-Q":
        return tuple(
            _format_quarter_label(quarter)
            for quarter in _report_quarter_labels_from_context(text, form_type=form_type)
        )
    if normalized_form == "10-K":
        return tuple(str(year) for year in sorted(set(_year_labels_from_context(text))))
    fallback = _context_label_text(text)
    return (fallback,) if fallback else ()


def _formula_period_context_for_report(value: Any, *, form_type: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized_form = _normal_report_form(form_type)
    if normalized_form == "10-Q":
        quarter_labels = _report_quarter_labels_from_context(text, form_type=form_type)
        if quarter_labels:
            return _compact_quarter_labels(quarter_labels)
    if normalized_form == "10-K":
        year_labels = _year_labels_from_context(text)
        if year_labels:
            return _compact_year_labels(year_labels)
    return _context_label_text(text)


def _context_before_detail_separator(value: str) -> str:
    return re.split(r"\s+[/|]\s+", value, maxsplit=1)[0].strip()


def _context_label_text(value: str) -> str:
    return "; ".join(
        _context_before_detail_separator(part.strip())
        for part in str(value or "").split(";")
        if part.strip()
    )


def _year_labels_from_context(value: str) -> list[int]:
    base = _context_label_text(value)
    return [
        int(match.group(1))
        for match in re.finditer(r"\b((?:19|20)\d{2})(?:\s*FY)?\b", base, flags=re.IGNORECASE)
    ]


def _quarter_labels_from_context(value: str) -> list[tuple[int, int]]:
    base = _context_label_text(value)
    return [
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(r"\b((?:19|20)\d{2})\s+Q([1-4])\b", base, flags=re.IGNORECASE)
    ]


def _report_quarter_labels_from_context(value: str, *, form_type: str) -> list[tuple[int, int]]:
    quarters: set[tuple[int, int]] = set(_quarter_labels_from_context(value))
    for start, end in _quarter_ranges_from_context(value):
        quarters.update(_expand_quarter_range(start, end))
    if _normal_report_form(form_type) == "10-Q":
        quarters = {quarter for quarter in quarters if quarter[1] != 4}
    return sorted(quarters)


def _quarter_ranges_from_context(value: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    base = _context_label_text(value)
    return [
        (
            (int(match.group(1)), int(match.group(2))),
            (int(match.group(3)), int(match.group(4))),
        )
        for match in re.finditer(
            r"\b((?:19|20)\d{2})\s+Q([1-4])\s*-\s*((?:19|20)\d{2})\s+Q([1-4])\b",
            base,
            flags=re.IGNORECASE,
        )
    ]


def _expand_quarter_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    start_index = _quarter_index(start)
    end_index = _quarter_index(end)
    if end_index < start_index:
        start_index, end_index = end_index, start_index
    return [_quarter_from_index(index) for index in range(start_index, end_index + 1)]


def _quarter_from_index(index: int) -> tuple[int, int]:
    year = (index - 1) // 4
    quarter = index - year * 4
    return year, quarter


def _format_formula_period_labels_for_report(labels: Sequence[str], *, form_type: str) -> str:
    normalized_form = _normal_report_form(form_type)
    unique_labels = tuple(dict.fromkeys(label for label in labels if label))
    if normalized_form == "10-K":
        years = [
            int(match.group(1))
            for label in unique_labels
            for match in re.finditer(r"\b((?:19|20)\d{2})\b", label)
        ]
        if years:
            return _compact_year_labels(years)
    if normalized_form == "10-Q":
        quarters = [
            quarter
            for label in unique_labels
            for quarter in _report_quarter_labels_from_context(label, form_type=form_type)
        ]
        if quarters:
            return _compact_quarter_labels(quarters)
    return _join_unique_texts(unique_labels)


def _first_formula_period_sort_value(value: str, *, form_type: str) -> int:
    normalized_form = _normal_report_form(form_type)
    if normalized_form == "10-Q":
        quarters = set(_report_quarter_labels_from_context(value, form_type=form_type))
        if quarters:
            return max(_quarter_index(quarter) for quarter in quarters)
    if normalized_form == "10-K":
        years = _year_labels_from_context(value)
        if years:
            return max(years)
    return 0


def _compact_year_labels(years: list[int]) -> str:
    ranges = _consecutive_ranges(sorted(set(years)))
    return ", ".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in ranges
    )


def _compact_quarter_labels(quarters: list[tuple[int, int]]) -> str:
    ordered = sorted(set(quarters))
    if not ordered:
        return ""
    ranges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    range_start = ordered[0]
    previous = ordered[0]
    for current in ordered[1:]:
        if _quarter_index(current) == _quarter_index(previous) + 1:
            previous = current
            continue
        ranges.append((range_start, previous))
        range_start = current
        previous = current
    ranges.append((range_start, previous))
    return ", ".join(
        _format_quarter_label(start)
        if start == end
        else f"{_format_quarter_label(start)} - {_format_quarter_label(end)}"
        for start, end in ranges
    )


def _consecutive_ranges(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    ranges: list[tuple[int, int]] = []
    start = values[0]
    previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = value
        previous = value
    ranges.append((start, previous))
    return ranges


def _quarter_index(value: tuple[int, int]) -> int:
    year, quarter = value
    return year * 4 + quarter


def _format_quarter_label(value: tuple[int, int]) -> str:
    year, quarter = value
    return f"{year} q{quarter}"


def _provider_label(row: dict[str, Any]) -> str:
    provider = str(row.get("provider_name") or "")
    model = str(row.get("model_name") or "")
    if provider and model:
        return f"{provider} ({model})"
    return provider or model


def _formula_expression_for_report(
    *,
    metric: str,
    row: dict[str, Any],
    components: str | None = None,
) -> str:
    if row.get("provider_status") == PROVIDER_STATUS_TARGET_ZERO:
        return f"{metric} = 0"
    components = str(components if components is not None else row.get("components") or "").strip()
    if components:
        return f"{metric} = {_component_formula_rhs(components)}"
    return _strip_concept_prefixes(row.get("formula_expression") or "")


def _component_formula_rhs(components: str) -> str:
    parts = [part.strip() for part in components.split(",") if part.strip()]
    if parts and parts[0].startswith("+ "):
        parts[0] = parts[0][2:]
    return " ".join(parts)


def _summary_rows_by_item(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("evidence_item") or ""): row for row in rows}


def _count_rows_with_value(rows: list[dict[str, Any]], column: str, value: str) -> int:
    return sum(row.get(column) == value for row in rows)


def _new_filing_summary(filings: tuple[FilingUpdateEvidence, ...]) -> str:
    if not filings:
        return "none"
    return _join_values(
        tuple(
            f"{filing.form_type} {filing.accession_number}"
            for filing in filings
        )
    )


def _join_sorted_values(values: set[str]) -> str:
    return _join_values(tuple(sorted(value for value in values if value)))


def _join_unique_texts(values: Sequence[str]) -> str:
    return "; ".join(dict.fromkeys(value for value in values if value))


_CONCEPT_PREFIX_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.-]*:([A-Za-z_][A-Za-z0-9_.-]*)")


def _strip_concept_prefixes(value: Any) -> str:
    return _CONCEPT_PREFIX_PATTERN.sub(r"\1", str(value or ""))


def _split_joined_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text == "none":
        return []
    return [part.strip() for part in text.split(",") if part.strip() and part.strip() != "none"]


def _update_check_needed(decision: SessionDecision) -> bool:
    return bool(decision.refresh_due_10k or decision.refresh_due_10q)


def _status_summary(decision: SessionDecision) -> str:
    if not decision.company_exists:
        return "company is not in local storage"
    if decision.status == "reused_local":
        return "local data reused; no SEC request made"
    if decision.status == "checked_no_update":
        return "SEC checked; no newer active-window filing found"
    if decision.status == "updated":
        return "SEC checked; new active-window filing data ingested"
    if decision.status == "refresh_failed_using_local_data":
        return "SEC check failed; local data reused"
    if decision.status == "initialized":
        return "company initialized from SEC"
    return decision.status


def _yes_no_unknown(value: bool | None) -> str:
    if value is None:
        return "not available"
    return _yes_no(value)


def _present_report(run: ExperimentRun, *, write_report: bool, full_report: bool) -> None:
    del write_report
    _write_report(run, full_report=full_report)


def _export_csv_artifacts(paths: ExperimentPaths, *, company_id: int | None) -> tuple[str, ...]:
    paths.exports_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    with connect_sqlite(paths.database) as connection:
        initialize_database(connection)
        export_jobs = [
            (
                "companies",
                "SELECT * FROM companies ORDER BY company_id",
                paths.exports_dir / "companies.csv",
            ),
            (
                "filings",
                "SELECT * FROM filings ORDER BY form_type, filing_date DESC",
                paths.exports_dir / "filings.csv",
            ),
            (
                "raw_xbrl_facts",
                "SELECT * FROM raw_xbrl_facts ORDER BY concept, end_date, accession_number, unit",
                paths.exports_dir / "raw_xbrl_facts.csv",
            ),
            (
                "financial_metrics",
                """
                SELECT *
                FROM financial_metrics
                ORDER BY statement_type, metric_name, fiscal_year DESC, fiscal_period DESC
                """,
                paths.exports_dir / "financial_metrics.csv",
            ),
            (
                "company_industry_labels",
                "SELECT * FROM company_industry_labels ORDER BY company_id, industry_label",
                paths.exports_dir / "company_industry_labels.csv",
            ),
            (
                "xbrl_concept_mappings",
                """
                SELECT *
                FROM xbrl_concept_mappings
                ORDER BY status, scope_type, scope_value, metric_name, confidence DESC
                """,
                paths.exports_dir / "xbrl_concept_mappings.csv",
            ),
        ]
        for label, query, path in export_jobs:
            try:
                _export_query(connection, query, path)
            except OSError as exc:
                warnings.append(f"CSV export skipped for {label}: {exc}")
        try:
            _export_rows(
                _traceability_sample(connection, company_id),
                paths.exports_dir / "metric_traceability_sample.csv",
            )
        except OSError as exc:
            warnings.append(f"CSV export skipped for metric_traceability_sample: {exc}")
    return tuple(warnings)


def _export_query(connection: sqlite3.Connection, query: str, path: Path) -> None:
    cursor = connection.execute(query)
    headers = [column[0] for column in cursor.description or ()]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if headers:
            writer.writerow(headers)
            writer.writerows(cursor)


def _export_rows(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if headers:
            writer.writeheader()
            writer.writerows(rows)


def _fetch_one(connection: sqlite3.Connection, query: str, params: Sequence[Any] = ()) -> dict[str, Any]:
    row = connection.execute(query, list(params)).fetchone()
    return dict(row) if row is not None else {}


def _fetch_all(
    connection: sqlite3.Connection,
    query: str,
    params: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    rows = connection.execute(query, list(params)).fetchall()
    return [dict(row) for row in rows]


def _markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["No rows to display."]
    headers = list(rows[0].keys())
    rendered_rows = [
        {header: _markdown_cell(header, row.get(header)) for header in headers}
        for row in rows
    ]
    widths = {
        header: max(3, len(header), *(len(row[header]) for row in rendered_rows))
        for header in headers
    }
    right_aligned = {
        header
        for header in headers
        if header not in {"metric_name", "statement_type"}
        and all(_is_numeric_table_cell(row[header]) for row in rendered_rows)
    }
    lines = [
        "| "
        + " | ".join(_pad_table_cell(header, header, widths, right_aligned) for header in headers)
        + " |",
        "| " + " | ".join("-" * widths[header] for header in headers) + " |",
    ]
    for row in rendered_rows:
        lines.append(
            "| "
            + " | ".join(
                _pad_table_cell(header, row[header], widths, right_aligned)
                for header in headers
            )
            + " |"
        )
    return lines


def _pad_table_cell(
    header: str,
    text: str,
    widths: dict[str, int],
    right_aligned: set[str],
) -> str:
    if header in right_aligned:
        return text.rjust(widths[header])
    return text.ljust(widths[header])


def _is_numeric_table_cell(text: str) -> bool:
    if not text:
        return True
    return all(_is_number_text(part.strip()) for part in text.split(";"))


def _is_number_text(text: str) -> bool:
    if not text:
        return True
    if text[-1].upper() in {"K", "M", "B", "T"}:
        text = text[:-1]
    if text[0] in {"-", "+"}:
        text = text[1:]
    if text.count(".") > 1:
        return False
    return text.replace(".", "", 1).isdigit()


def _markdown_cell(header: str, value: Any) -> str:
    if value is None:
        return ""
    text = _sanitize_markdown_cell_text(value)
    if _should_format_presentation_number(header):
        text = "; ".join(_format_presentation_number(part.strip()) for part in text.split(";"))
    if len(text) > MARKDOWN_CELL_MAX_CHARS:
        return text[: MARKDOWN_CELL_MAX_CHARS - 3] + "..."
    return text


def _sanitize_markdown_cell_text(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text.replace("|", "/")


def _should_format_presentation_number(header: str) -> bool:
    normalized_header = header.lower()
    if normalized_header in PRESENTATION_NUMBER_EXCLUDED_HEADERS:
        return False
    if normalized_header.endswith(("_id", "_ids", "_hash")):
        return False
    return "accession" not in normalized_header


def _format_presentation_number(value: Any) -> str:
    text = str(value).strip()
    decimal_value = _parse_decimal_text(text)
    if decimal_value is None:
        return text
    absolute_value = abs(decimal_value)
    for factor, suffix in PRESENTATION_NUMBER_SUFFIXES:
        if absolute_value >= factor:
            try:
                scaled_value = (decimal_value / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except InvalidOperation:
                return text
            return f"{scaled_value:.2f}{suffix}"
    if decimal_value != decimal_value.to_integral_value():
        try:
            rounded_value = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return text
        return f"{rounded_value:.2f}"
    return text


def _parse_decimal_text(value: str) -> Decimal | None:
    text = str(value).strip().replace(",", "")
    if not text or text[-1].upper() in {"K", "M", "B", "T"}:
        return None
    try:
        decimal_value = Decimal(text)
    except InvalidOperation:
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _date_from_text(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _report_decimal(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _join_values(values: Sequence[object]) -> str:
    return ", ".join(str(value) for value in values if value is not None and str(value) != "") or ""


def _join(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _error_run(
    *,
    ticker: str,
    paths: ExperimentPaths,
    error: Exception,
    sec_user_agent_configured: bool,
) -> ExperimentRun:
    normalized_ticker = ticker.strip().upper() or "UNKNOWN"
    snapshot_warning = ""
    try:
        snapshot = _snapshot(paths.database, normalized_ticker, formula_proposals_enabled=False)
    except (OSError, sqlite3.Error, ValueError) as snapshot_error:
        snapshot = _empty_snapshot()
        snapshot_warning = f"Local storage snapshot unavailable during error report: {snapshot_error}"
    company_exists = bool(snapshot.get("company"))
    return ExperimentRun(
        ticker=normalized_ticker,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        sec_user_agent_configured=sec_user_agent_configured,
        paths=paths,
        company_existed_before_setup=company_exists,
        setup_status="experiment_error",
        setup_sec_checked=False,
        setup_snapshot=snapshot,
        session_before_snapshot=snapshot,
        session_after_snapshot=snapshot,
        session_decision=SessionDecision(
            company_exists=company_exists,
            status="experiment_error",
            sec_checked=False,
            refresh_due_10k=None,
            refresh_due_10q=None,
            new_filings=(),
        ),
        warnings=(snapshot_warning,) if snapshot_warning else (),
        error=str(error),
    )


if __name__ == "__main__":
    raise SystemExit(main())
