"""Manual examination harness for the Plan 2.5 company ingestion workflow."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings, load_settings
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
    target_facts_for_industry_labels,
)
from src.storage import CompanyRepository, connect_sqlite, initialize_database

EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "MS2_5"
EXPERIMENT_STORAGE_DIR = PROJECT_ROOT / "experiments" / "storage"
DEFAULT_DB_PATH = EXPERIMENT_STORAGE_DIR / "experiment.db"
DEFAULT_REPORT_PATH = EXPERIMENT_DIR / "experiment_report.md"
DEFAULT_FILINGS_DIR = EXPERIMENT_STORAGE_DIR / "filings"
DEFAULT_EXPORTS_DIR = PROJECT_ROOT / "data" / "exports" / "ms2_5"
FORMS = ("10-K", "10-Q")
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
    "frame",
    "id",
    "local_path",
    "metric_id",
    "next_check_date_10k",
    "next_check_date_10q",
    "raw_fact_id",
    "sic",
    "source_raw_fact_id",
    "start_date",
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

    try:
        settings = _experiment_settings(args.env_file, paths)
        if not settings.sec_user_agent:
            raise SecConfigurationError("SEC_USER_AGENT is required for live SEC experiment runs")
        run = run_experiment(ticker=ticker, settings=settings, paths=paths)
    except (SecConfigurationError, SecIngestionError, TickerNotFoundError, FilingNotFoundError, ValueError) as exc:
        run = _error_run(ticker=ticker, paths=paths, error=exc)
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
        session_after_snapshot = _snapshot(paths.database, normalized_ticker)
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
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH), help=argparse.SUPPRESS)
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
    return parser.parse_args(argv)


def _paths_from_args(args: argparse.Namespace) -> ExperimentPaths:
    return ExperimentPaths(
        database=Path(args.db_path),
        report=Path(args.report_path),
        filings_dir=Path(args.filings_dir),
        exports_dir=Path(args.exports_dir),
    )


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


def _snapshot(database: Path, ticker: str) -> dict[str, Any]:
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
        industry_assignment = _company_industry_label_assignment(company, observed_concepts)
        target_raw_fact_coverage = _target_raw_fact_coverage(
            connection,
            company_id=company_id,
            cik=cik,
            assignment=industry_assignment,
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
            "metric_counts_by_statement": _metric_counts_by_statement(connection, company_id),
            "metric_lineage_summary": _metric_lineage_summary(connection, company_id),
            "raw_fact_mapping_coverage": _raw_fact_mapping_coverage(connection, company_id, cik),
            "alternate_xbrl_tags": _alternate_xbrl_tags(connection, company_id),
            "unknown_xbrl_concepts": _unknown_xbrl_concepts(connection, cik),
            "metric_sample": _metric_sample(connection, company_id),
            "traceability_sample": _traceability_sample(connection, company_id),
            "quality_flags": _quality_flags(connection, cik),
        }


def _empty_snapshot() -> dict[str, Any]:
    return {
        "company": {},
        "counts": {"companies": 0, "filings": 0, "raw_xbrl_facts": 0, "financial_metrics": 0},
        "filings": [],
        "filings_by_form": {form_type: () for form_type in FORMS},
        "active_filings_by_form": {form_type: 0 for form_type in FORMS},
        "company_industry_labels": [],
        "target_raw_fact_coverage": [],
        "found_target_facts": [],
        "missing_target_facts": [],
        "found_unmapped_target_facts": [],
        "metric_counts_by_statement": [],
        "metric_lineage_summary": [],
        "raw_fact_mapping_coverage": [],
        "alternate_xbrl_tags": [],
        "unknown_xbrl_concepts": [],
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
        for table in ("companies", "filings", "raw_xbrl_facts", "financial_metrics")
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


def _company_industry_label_assignment(
    company: dict[str, Any],
    observed_concepts: Sequence[str],
) -> CompanyIndustryLabelAssignment:
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
        notes = "; ".join(
            note
            for note in (
                target.notes,
                label_review_note,
                "observed but did not create financial_metrics rows" if status == STATUS_FOUND_UNMAPPED else "",
            )
            if note
        )
        rows.append(
            {
                "industry_label": target.industry_label,
                "target_raw_concept": target.raw_concept,
                "taxonomy": target.taxonomy,
                "internal_metric_name": target.internal_metric_name,
                "statement_type": target.statement_type,
                "required_for_core": _yes_no(target.required_for_core),
                "required_for_specialized_indicators": _yes_no(target.required_for_specialized_indicators),
                "status": status,
                "observed_rows": observed_rows,
                "mapped_rows": mapped_rows,
                "unit_count": observed.get("unit_count") or 0,
                "forms": observed.get("forms") or "",
                "latest_filing_date": observed.get("latest_filing_date") or "",
                "notes": notes,
            }
        )
    return rows


def _target_coverage_status(observed_rows: int, mapped_rows: int) -> str:
    if observed_rows <= 0:
        return STATUS_MISSING_TARGET
    if mapped_rows > 0:
        return STATUS_FOUND_MAPPED
    return STATUS_FOUND_UNMAPPED


def _target_rows_with_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
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


def _raw_fact_mapping_coverage(
    connection: sqlite3.Connection,
    company_id: int | None,
    cik: str | None,
) -> list[dict[str, Any]]:
    if company_id is None or not cik:
        return []
    concept_clause = _concept_in_clause()
    concept_params = _base_metric_concepts()
    raw_summary = _fetch_one(
        connection,
        f"""
        SELECT
            COUNT(*) AS raw_fact_rows,
            COUNT(DISTINCT concept) AS distinct_raw_concepts,
            SUM(CASE WHEN concept IN ({concept_clause}) THEN 1 ELSE 0 END)
                AS raw_facts_with_supported_concepts,
            SUM(CASE WHEN concept NOT IN ({concept_clause}) THEN 1 ELSE 0 END)
                AS unknown_raw_fact_rows,
            COUNT(DISTINCT CASE WHEN concept NOT IN ({concept_clause}) THEN concept END)
                AS unknown_raw_concepts
        FROM raw_xbrl_facts
        WHERE cik = ?
        """,
        [*concept_params, *concept_params, *concept_params, cik],
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
    raw_fact_rows = int(raw_summary.get("raw_fact_rows") or 0)
    distinct_raw_concepts = int(raw_summary.get("distinct_raw_concepts") or 0)
    raw_facts_with_supported_concepts = int(raw_summary.get("raw_facts_with_supported_concepts") or 0)
    unknown_raw_fact_rows = int(raw_summary.get("unknown_raw_fact_rows") or 0)
    unknown_raw_concepts = int(raw_summary.get("unknown_raw_concepts") or 0)
    financial_metric_rows = int(mapped_summary.get("financial_metric_rows") or 0)
    mapped_raw_facts = int(mapped_summary.get("mapped_raw_facts") or 0)
    mapped_raw_concepts = int(mapped_summary.get("mapped_raw_concepts") or 0)
    supported_but_not_mapped = max(raw_facts_with_supported_concepts - mapped_raw_facts, 0)
    return [
        {
            "coverage_item": "raw XBRL facts downloaded/stored for ticker",
            "count": raw_fact_rows,
            "note": "full normalized SEC companyfacts archive",
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
            "count": len(BASE_METRIC_MAPPINGS),
            "note": f"maps into {len({mapping.metric_name for mapping in BASE_METRIC_MAPPINGS.values()})} business metrics",
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


def _unknown_xbrl_concepts(connection: sqlite3.Connection, cik: str | None) -> list[dict[str, Any]]:
    if not cik:
        return []
    concept_clause = _concept_in_clause()
    return _fetch_all(
        connection,
        f"""
        SELECT
            concept AS raw_xbrl_concept,
            COALESCE(MAX(label), '') AS label,
            taxonomy,
            COUNT(*) AS raw_fact_rows,
            COUNT(DISTINCT unit) AS unit_count,
            COALESCE(GROUP_CONCAT(DISTINCT form), '') AS forms,
            MAX(end_date) AS latest_end_date,
            MAX(filed_date) AS latest_filed_date
        FROM raw_xbrl_facts
        WHERE cik = ? AND concept NOT IN ({concept_clause})
        GROUP BY taxonomy, concept
        ORDER BY raw_fact_rows DESC, raw_xbrl_concept
        """,
        [cik, *_base_metric_concepts()],
    )


def _concept_in_clause() -> str:
    return ", ".join("?" for _ in BASE_METRIC_MAPPINGS)


def _base_metric_concepts() -> tuple[str, ...]:
    return tuple(sorted(BASE_METRIC_MAPPINGS))


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


def _metric_lineage_rows(connection: sqlite3.Connection, company_id: int | None) -> list[dict[str, Any]]:
    if company_id is None:
        return []
    return _fetch_all(
        connection,
        """
        SELECT
            c.ticker,
            c.cik,
            m.metric_id,
            m.statement_type,
            m.metric_name,
            f.concept AS raw_xbrl_concept,
            f.label AS raw_xbrl_label,
            m.fiscal_year,
            m.fiscal_period,
            m.start_date,
            m.end_date,
            m.value_numeric,
            m.unit,
            m.period_type,
            m.is_active_window,
            m.accession_number,
            fi.form_type,
            fi.filing_date,
            m.raw_fact_id,
            f.quality_flags AS raw_quality_flags
        FROM financial_metrics AS m
        LEFT JOIN companies AS c
            ON c.company_id = m.company_id
        LEFT JOIN raw_xbrl_facts AS f
            ON f.id = m.raw_fact_id
        LEFT JOIN filings AS fi
            ON fi.filing_id = m.filing_id
        WHERE m.company_id = ?
        ORDER BY m.statement_type, m.metric_name, m.fiscal_year DESC, m.fiscal_period DESC, m.accession_number
        """,
        [company_id],
    )


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


def format_lineage_report(run: ExperimentRun) -> str:
    """Render the financial metric data lineage view as a text report."""
    rows = _lineage_rows_for_run(run)
    annual_rows = _pivot_metric_rows(rows, annual=True)
    quarterly_rows = _pivot_metric_rows(rows, annual=False)
    lines = [
        "Milestone 2.5 Financial Metric Data Lineage View",
        "",
        "Run Context:",
        f"  ticker: {run.ticker}",
        f"  run timestamp: {run.run_timestamp}",
        f"  database: {run.paths.database}",
        f"  saved report: {run.paths.report}",
    ]
    lines.extend(["", "Company Industry Labels:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("company_industry_labels") or []))
    lines.extend(["", "Raw Fact Mapping Coverage (Highlighted):"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("raw_fact_mapping_coverage") or []))
    lines.extend(["", "Target Raw Fact Coverage:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("target_raw_fact_coverage") or []))
    lines.extend(["", "Found Target Facts:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("found_target_facts") or []))
    lines.extend(["", "Missing Target Facts:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("missing_target_facts") or []))
    lines.extend(["", "Found But Unmapped Target Facts:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("found_unmapped_target_facts") or []))
    lines.extend(["", "Alternate SEC/XBRL Tags For Same Business Metric:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("alternate_xbrl_tags") or []))
    lines.extend(["", "Annual XBRL Financial Metrics:"])
    lines.extend(_markdown_table(annual_rows))
    lines.extend(["", "Quarterly XBRL Financial Metrics:"])
    lines.extend(_markdown_table(quarterly_rows))
    lines.extend(["", "Unknown SEC/XBRL Concepts Not Mapped To Base Metrics:"])
    lines.extend(_markdown_table(run.session_after_snapshot.get("unknown_xbrl_concepts") or []))
    lines.extend(
        [
            "",
            "Full Evidence:",
            f"  SQLite database: {run.paths.database}",
            "  database table: raw_xbrl_facts",
            "  database table: financial_metrics",
            f"  companies CSV: {run.paths.exports_dir / 'companies.csv'}",
            f"  filings CSV: {run.paths.exports_dir / 'filings.csv'}",
            f"  raw facts CSV: {run.paths.exports_dir / 'raw_xbrl_facts.csv'}",
            f"  financial metrics CSV: {run.paths.exports_dir / 'financial_metrics.csv'}",
            f"  traceability sample CSV: {run.paths.exports_dir / 'metric_traceability_sample.csv'}",
            f"  filing downloads: {run.paths.filings_dir}",
            f"  saved report with appended lineage section: {run.paths.report}",
            "",
            "Expected Outcome:",
            "  A human can scan annual and quarterly XBRL-derived financial",
            "  metrics with metrics as rows and periods as columns.",
        ]
    )
    return "\n".join(lines)


def _pivot_metric_rows(rows: list[dict[str, Any]], *, annual: bool) -> list[dict[str, Any]]:
    period_labels: set[str] = set()
    grouped: dict[tuple[str, str], dict[str, list[str]]] = {}
    quarterly_end_dates = {} if annual else _latest_end_dates_by_fiscal_period(rows)
    for row in rows:
        period_label = _pivot_period_label(
            row,
            annual=annual,
            quarterly_end_dates=quarterly_end_dates,
        )
        if period_label is None:
            continue
        metric_name = str(row.get("metric_name") or "unknown_metric")
        statement_type = str(row.get("statement_type") or "unknown_statement")
        value = row.get("value_numeric")
        if value is None:
            continue
        period_labels.add(period_label)
        values = grouped.setdefault((metric_name, statement_type), {}).setdefault(period_label, [])
        value_text = str(value)
        if value_text not in values:
            values.append(value_text)

    ordered_periods = sorted(period_labels, key=_pivot_period_sort_key, reverse=True)
    pivot_rows: list[dict[str, Any]] = []
    for metric_name, statement_type in sorted(grouped, key=lambda key: (key[1], key[0])):
        pivot_row: dict[str, Any] = {
            "metric_name": metric_name,
            "statement_type": statement_type,
        }
        for period_label in ordered_periods:
            pivot_row[period_label] = _pivot_cell(grouped[(metric_name, statement_type)].get(period_label, []))
        pivot_rows.append(pivot_row)
    return pivot_rows


def _latest_end_dates_by_fiscal_period(
    rows: list[dict[str, Any]],
) -> dict[tuple[int, str], datetime]:
    latest: dict[tuple[int, str], datetime] = {}
    for row in rows:
        fiscal_year = _as_int(row.get("fiscal_year"))
        fiscal_period = str(row.get("fiscal_period") or "").upper()
        end_date = _parse_date(row.get("end_date"))
        if fiscal_year is None or not fiscal_period or end_date is None:
            continue
        key = (fiscal_year, fiscal_period)
        if key not in latest or end_date > latest[key]:
            latest[key] = end_date
    return latest


def _pivot_period_label(
    row: dict[str, Any],
    *,
    annual: bool,
    quarterly_end_dates: dict[tuple[int, str], datetime] | None = None,
) -> str | None:
    fiscal_year = _as_int(row.get("fiscal_year"))
    fiscal_period = str(row.get("fiscal_period") or "").upper()
    if fiscal_year is None or not fiscal_period:
        return None
    if annual:
        if fiscal_period != "FY":
            return None
        if not _end_date_matches_period(row.get("end_date"), fiscal_year, quarter=None):
            return None
        if not _duration_matches_period(row, annual=True):
            return None
        return str(fiscal_year)

    if fiscal_period == "FY":
        return None
    quarter = _quarter_number(fiscal_period)
    if quarter is None:
        return None
    expected_end_date = (quarterly_end_dates or {}).get((fiscal_year, fiscal_period))
    if expected_end_date is None:
        if not _end_date_matches_period(row.get("end_date"), fiscal_year, quarter=quarter):
            return None
    else:
        row_end_date = _parse_date(row.get("end_date"))
        if row_end_date is not None and row_end_date != expected_end_date:
            return None
    if not _duration_matches_period(row, annual=False):
        return None
    return f"{fiscal_year} Q{quarter}"


def _end_date_matches_period(value: Any, fiscal_year: int, *, quarter: int | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    parts = text.split("-")
    if len(parts) < 2:
        return True
    try:
        end_year = int(parts[0])
        end_month = int(parts[1])
    except ValueError:
        return True
    if end_year != fiscal_year:
        return False
    if quarter is None:
        return True
    return ((end_month - 1) // 3) + 1 == quarter


def _duration_matches_period(row: dict[str, Any], *, annual: bool) -> bool:
    if str(row.get("period_type") or "").lower() != "duration":
        return True
    start_date = _parse_date(row.get("start_date"))
    end_date = _parse_date(row.get("end_date"))
    if start_date is None or end_date is None:
        return True
    days = (end_date - start_date).days + 1
    if annual:
        return days >= 300
    return 60 <= days <= 120


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _pivot_period_sort_key(label: str) -> tuple[int, int]:
    parts = label.split()
    year = _as_int(parts[0]) if parts else None
    if len(parts) == 1:
        return (year or 0, 0)
    quarter = _quarter_number(parts[1])
    return (year or 0, quarter or 0)


def _quarter_number(value: str) -> int | None:
    value = value.strip().upper()
    if len(value) == 2 and value.startswith("Q") and value[1].isdigit():
        quarter = int(value[1])
        if 1 <= quarter <= 4:
            return quarter
    return None


def _pivot_cell(values: Sequence[str]) -> str:
    return "; ".join(_format_presentation_number(value) for value in values)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _lineage_rows_for_run(run: ExperimentRun) -> list[dict[str, Any]]:
    company_id = _snapshot_company_id(run.session_after_snapshot)
    if company_id is None or not run.paths.database.exists():
        return []
    with connect_sqlite(run.paths.database) as connection:
        initialize_database(connection)
        return _metric_lineage_rows(connection, company_id)


def format_report(run: ExperimentRun, *, report_output: str = "file") -> str:
    """Render a compact Markdown report for manual inspection."""
    lines = [
        "# Milestone 2.5 Live SEC Experiment Report",
        "",
        "## Human Question",
        "",
        "For a company I choose, what does Plan 2.5 ingestion do during setup",
        "and during the next already-ingested session: local existence, refresh",
        "due status, SEC update check, newly ingested filings, next check dates,",
        "and stored evidence?",
        "",
        "## Run Context",
        "",
    ]
    lines.extend(
        _definition_list(
            {
                "ticker": run.ticker,
                "run timestamp": run.run_timestamp,
                "database": run.paths.database,
                "report output": report_output,
                "report": run.paths.report,
                "filings directory": run.paths.filings_dir,
                "csv export directory": run.paths.exports_dir,
                "SEC_USER_AGENT configured": _yes_no(run.sec_user_agent_configured),
            }
        )
    )
    if run.error:
        lines.extend(["", "## Execution Warning", "", run.error])
    if run.warnings:
        lines.extend(["", "## Source Quality Warnings", ""])
        lines.extend(f"- {warning}" for warning in run.warnings)

    lines.extend(["", "## Setup Ingestion", ""])
    lines.extend(
        _definition_list(
            {
                "company existed before setup": _yes_no(run.company_existed_before_setup),
                "setup status": run.setup_status,
                "SEC checked during setup": _yes_no(run.setup_sec_checked),
            }
        )
    )
    lines.extend(_snapshot_sections(run.setup_snapshot))

    lines.extend(["", "## Already-Ingested Session Check", ""])
    lines.extend(_session_decision_sections(run))
    return "\n".join(lines)


def format_saved_report(run: ExperimentRun, *, full_report: bool = False) -> str:
    """Render the saved experiment report, including the former terminal summary."""
    lines = [
        "# Milestone 2.5 Live SEC Experiment Report",
        "",
        "## Compact Summary",
        "",
        "```text",
        format_compact_report(run, full_report=full_report),
        "```",
    ]
    if full_report:
        detailed_lines = format_report(run, report_output="saved compact + detailed report").splitlines()
        if detailed_lines[:2] == ["# Milestone 2.5 Live SEC Experiment Report", ""]:
            detailed_lines = detailed_lines[2:]
        lines.extend([""])
        lines.extend(detailed_lines)
    lines.extend(
        [
            "",
            "```text",
            format_lineage_report(run),
            "```",
        ]
    )
    return "\n".join(lines)


def format_compact_report(run: ExperimentRun, *, full_report: bool = False) -> str:
    """Render a concise run summary for quick manual inspection."""
    setup_company = run.setup_snapshot.get("company") or {}
    session_after_company = run.session_after_snapshot.get("company") or {}
    report_output = "saved compact + detailed report" if full_report else "saved compact report"
    lines = [
        "Milestone 2.5 Plan 2.5 Ingestion Examination",
        "",
        "Run Context",
        f"  ticker: {run.ticker}",
        f"  run timestamp: {run.run_timestamp}",
        "  mode: live SEC, shared isolated experiment storage",
        f"  SEC_USER_AGENT configured: {_yes_no(run.sec_user_agent_configured)}",
        f"  report output: {report_output}",
        "",
        "Initial Setup Ingestion",
        f"  company existed before setup: {_yes_no(run.company_existed_before_setup)}",
        f"  setup status: {run.setup_status}",
        f"  SEC checked during setup: {_yes_no(run.setup_sec_checked)}",
        f"  CIK: {setup_company.get('cik') or 'not available'}",
        f"  company name: {setup_company.get('name') or 'not available'}",
        "",
        "Already-Ingested Session Check",
    ]
    lines.extend(_session_decision_lines(run, indent="  "))
    lines.extend(["", "Company Industry Labels"])
    lines.extend(_compact_company_industry_labels(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Stored Rows After Session"])
    lines.extend(_compact_counts(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Active Window After Session"])
    lines.extend(_compact_active_window(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Raw Fact Mapping Coverage"])
    lines.extend(_compact_raw_fact_mapping_coverage(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Target Raw Fact Coverage"])
    lines.extend(_compact_target_raw_fact_coverage(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Base Metrics After Session"])
    lines.extend(_compact_metric_counts(run.session_after_snapshot, indent="  "))

    if run.error:
        lines.extend(["", "Execution Warning", f"  {run.error}"])
    if run.warnings:
        lines.extend(["", "Source And Export Warnings"])
        lines.extend(f"  - {warning}" for warning in run.warnings)

    lines.extend(
        [
            "",
            "More Detail",
            (
                "  Detailed Markdown sections are included below this compact summary."
                if full_report
                else "  Add --full-report to include detailed Markdown sections in this saved report."
            ),
        ]
    )
    return "\n".join(lines)


def _session_decision_lines(run: ExperimentRun, *, indent: str) -> list[str]:
    decision = run.session_decision
    before_company = run.session_before_snapshot.get("company") or {}
    lines = [
        f"{indent}company in system: {_yes_no(decision.company_exists)}",
    ]
    if not decision.company_exists:
        lines.extend(
            [
                f"{indent}update check needed this session: not applicable",
                f"{indent}SEC update check performed: no",
                f"{indent}SEC result: company is not in local storage",
                f"{indent}new filings ingested this session: none",
            ]
        )
        return lines

    lines.extend(
        [
            f"{indent}update check needed this session: {_yes_no(_update_check_needed(decision))}",
            (
                f"{indent}10-K check due: {_yes_no_unknown(decision.refresh_due_10k)} "
                f"(next check date before session: {before_company.get('next_check_date_10k') or 'not available'})"
            ),
            (
                f"{indent}10-Q check due: {_yes_no_unknown(decision.refresh_due_10q)} "
                f"(next check date before session: {before_company.get('next_check_date_10q') or 'not available'})"
            ),
            f"{indent}SEC update check performed: {_yes_no(decision.sec_checked)}",
            f"{indent}SEC result: {_status_summary(decision)}",
        ]
    )
    lines.extend(_new_filing_lines(decision.new_filings, indent=indent))
    return lines


def _session_decision_sections(run: ExperimentRun) -> list[str]:
    decision = run.session_decision
    before_company = run.session_before_snapshot.get("company") or {}
    after_company = run.session_after_snapshot.get("company") or {}
    rows: list[dict[str, Any]] = [
        {"field": "company in system", "value": _yes_no(decision.company_exists)},
        {
            "field": "update check needed this session",
            "value": "not applicable" if not decision.company_exists else _yes_no(_update_check_needed(decision)),
        },
        {
            "field": "10-K check due",
            "value": (
                "not applicable"
                if not decision.company_exists
                else f"{_yes_no_unknown(decision.refresh_due_10k)}; before={before_company.get('next_check_date_10k') or 'not available'}"
            ),
        },
        {
            "field": "10-Q check due",
            "value": (
                "not applicable"
                if not decision.company_exists
                else f"{_yes_no_unknown(decision.refresh_due_10q)}; before={before_company.get('next_check_date_10q') or 'not available'}"
            ),
        },
        {"field": "SEC update check performed", "value": _yes_no(decision.sec_checked)},
        {"field": "SEC result", "value": _status_summary(decision)}
    ]
    lines = _markdown_table(rows)
    lines.extend(["", "### New Filings Ingested During Session", ""])
    lines.extend(_markdown_table([_filing_evidence_row(filing) for filing in decision.new_filings]))
    lines.extend(["", "### Stored Row Deltas During Session", ""])
    lines.extend(_before_after_counts(run.session_before_snapshot, run.session_after_snapshot))
    lines.extend(["", "### Stored Evidence After Session", ""])
    lines.extend(_snapshot_sections(run.session_after_snapshot))
    return lines


def _new_filing_lines(filings: tuple[FilingUpdateEvidence, ...], *, indent: str) -> list[str]:
    if not filings:
        return [f"{indent}new filings ingested this session: none"]
    lines = [f"{indent}new filings ingested this session:"]
    lines.extend(
        (
            f"{indent}  - {filing.form_type} accession {filing.accession_number}; "
            f"filed {filing.filing_date}; local path {filing.local_path}"
        )
        for filing in filings
    )
    return lines


def _filing_evidence_row(filing: FilingUpdateEvidence) -> dict[str, Any]:
    return {
        "form": filing.form_type,
        "accession": filing.accession_number,
        "filing_date": filing.filing_date,
        "fiscal_year": filing.fiscal_year,
        "fiscal_period": filing.fiscal_period,
        "local_path": filing.local_path,
    }


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


def _compact_counts(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    counts = snapshot.get("counts") or {}
    return [f"{indent}{table}: {_format_presentation_number(count)}" for table, count in counts.items()]


def _compact_active_window(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    active = snapshot.get("active_filings_by_form") or {}
    accessions = snapshot.get("filings_by_form") or {}
    return [
        f"{indent}{form_type}: {_format_presentation_number(active.get(form_type, 0))} active filings; "
        f"{_format_presentation_number(len(accessions.get(form_type, ())))} local accessions"
        for form_type in FORMS
    ]


def _compact_metric_counts(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    rows = snapshot.get("metric_counts_by_statement") or []
    if not rows:
        return [f"{indent}none"]
    return [
        f"{indent}{row['statement_type']}: "
        f"{_format_presentation_number(row['total_metrics'])} total, "
        f"{_format_presentation_number(row['active_metrics'])} active"
        for row in rows
    ]


def _compact_raw_fact_mapping_coverage(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    rows = snapshot.get("raw_fact_mapping_coverage") or []
    if not rows:
        return [f"{indent}none"]
    by_item = {row["coverage_item"]: row for row in rows}
    selected_items = (
        "raw XBRL facts downloaded/stored for ticker",
        "raw facts mapped into financial_metrics",
        "raw facts not mapped into financial_metrics",
        "distinct raw XBRL concepts observed",
        "distinct unknown raw concepts",
        "supported SEC/XBRL tags in mapping catalog",
    )
    lines = []
    for item in selected_items:
        row = by_item.get(item)
        if row is None:
            continue
        note = f" ({row['note']})" if row.get("note") else ""
        lines.append(f"{indent}{item}: {_format_presentation_number(row['count'])}{note}")
    return lines or [f"{indent}none"]


def _compact_company_industry_labels(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    rows = snapshot.get("company_industry_labels") or []
    if not rows:
        return [f"{indent}none"]
    row = rows[0]
    return [
        f"{indent}assigned labels: {row.get('assigned_industry_labels') or 'none'}",
        f"{indent}label status: {row.get('label_status') or 'not available'}",
        f"{indent}assignment source: {row.get('assignment_source') or 'not available'}",
        f"{indent}assignment reason: {row.get('assignment_reason') or 'not available'}",
    ]


def _compact_target_raw_fact_coverage(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    rows = snapshot.get("target_raw_fact_coverage") or []
    if not rows:
        return [f"{indent}none"]
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [f"{indent}target concepts checked: {_format_presentation_number(len(rows))}"]
    for status, count in sorted(status_counts.items()):
        lines.append(f"{indent}{status}: {_format_presentation_number(count)}")
    return lines


def _snapshot_sections(snapshot: dict[str, Any]) -> list[str]:
    lines: list[str] = ["", "### Company State", ""]
    lines.extend(_markdown_table([snapshot["company"]] if snapshot["company"] else []))
    lines.extend(["", "### Company Industry Labels", ""])
    lines.extend(_markdown_table(snapshot["company_industry_labels"]))
    lines.extend(["", "### Filing Inventory", ""])
    lines.extend(_markdown_table(snapshot["filings"][:8]))
    lines.extend(["", "### Raw Fact And Metric Counts", ""])
    lines.extend(_count_table(snapshot))
    lines.extend(["", "### Raw Fact Mapping Coverage", ""])
    lines.extend(_markdown_table(snapshot["raw_fact_mapping_coverage"]))
    lines.extend(["", "### Target Raw Fact Coverage", ""])
    lines.extend(_markdown_table(snapshot["target_raw_fact_coverage"]))
    lines.extend(["", "### Found Target Facts", ""])
    lines.extend(_markdown_table(snapshot["found_target_facts"]))
    lines.extend(["", "### Missing Target Facts", ""])
    lines.extend(_markdown_table(snapshot["missing_target_facts"]))
    lines.extend(["", "### Found But Unmapped Target Facts", ""])
    lines.extend(_markdown_table(snapshot["found_unmapped_target_facts"]))
    lines.extend(["", "### Active Window", ""])
    lines.extend(_active_window_lines(snapshot))
    lines.extend(["", "### Financial Metric Data Lineage View", ""])
    lines.extend(
        [
            "This table summarizes raw XBRL concepts, system mappings, and",
            "financial_metrics availability. Annual and quarterly XBRL metric",
            "tables are written to the financial metric lineage text section.",
            "",
        ]
    )
    lines.extend(_markdown_table(snapshot["metric_lineage_summary"]))
    lines.extend(["", "### Alternate SEC/XBRL Tags For Same Business Metric", ""])
    lines.extend(_markdown_table(snapshot["alternate_xbrl_tags"]))
    lines.extend(["", "### Unknown SEC/XBRL Concepts Not Mapped To Base Metrics", ""])
    lines.extend(_markdown_table(snapshot["unknown_xbrl_concepts"]))
    lines.extend(["", "### Compact financial_metrics Sample", ""])
    lines.extend(_markdown_table(snapshot["metric_sample"]))
    lines.extend(["", "### Compact Traceability Sample", ""])
    lines.extend(_markdown_table(snapshot["traceability_sample"]))
    if snapshot["quality_flags"]:
        lines.extend(["", "### Raw Fact Quality Flags", ""])
        lines.extend(f"- {flag}" for flag in snapshot["quality_flags"])
    return lines


def _count_table(snapshot: dict[str, Any]) -> list[str]:
    counts = snapshot["counts"]
    rows = [{"table": table, "rows": count} for table, count in counts.items()]
    return _markdown_table(rows)


def _active_window_lines(snapshot: dict[str, Any]) -> list[str]:
    rows = [
        {
            "form": form_type,
            "active filings": snapshot["active_filings_by_form"].get(form_type, 0),
            "local accessions": _join(snapshot["filings_by_form"].get(form_type, ())),
        }
        for form_type in FORMS
    ]
    lines = _markdown_table(rows)
    if snapshot["metric_counts_by_statement"]:
        lines.extend(["", "Metric counts by statement:", ""])
        lines.extend(_markdown_table(snapshot["metric_counts_by_statement"]))
    return lines


def _before_after_counts(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    rows = []
    for table in before["counts"]:
        rows.append(
            {
                "table": table,
                "before": before["counts"][table],
                "after": after["counts"][table],
                "delta": after["counts"][table] - before["counts"][table],
            }
        )
    return _markdown_table(rows)


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


def _definition_list(values: dict[str, object]) -> list[str]:
    return [f"- {name}: {value}" for name, value in values.items()]


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
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "/")
    if _should_format_presentation_number(header):
        text = "; ".join(_format_presentation_number(part.strip()) for part in text.split(";"))
    if len(text) > 120:
        return text[:117] + "..."
    return text


def _should_format_presentation_number(header: str) -> bool:
    return header.lower() not in PRESENTATION_NUMBER_EXCLUDED_HEADERS


def _format_presentation_number(value: Any) -> str:
    text = str(value).strip()
    decimal_value = _parse_decimal_text(text)
    if decimal_value is None:
        return text
    absolute_value = abs(decimal_value)
    for factor, suffix in PRESENTATION_NUMBER_SUFFIXES:
        if absolute_value >= factor:
            scaled_value = (decimal_value / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{scaled_value:.2f}{suffix}"
    if decimal_value != decimal_value.to_integral_value():
        rounded_value = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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


def _join(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _error_run(
    *,
    ticker: str,
    paths: ExperimentPaths,
    error: Exception,
) -> ExperimentRun:
    return ExperimentRun(
        ticker=ticker.strip().upper() or "UNKNOWN",
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        sec_user_agent_configured=False,
        paths=paths,
        company_existed_before_setup=False,
        setup_status="experiment_error",
        setup_sec_checked=False,
        setup_snapshot=_empty_snapshot(),
        session_before_snapshot=_empty_snapshot(),
        session_after_snapshot=_empty_snapshot(),
        session_decision=SessionDecision(
            company_exists=False,
            status="experiment_error",
            sec_checked=False,
            refresh_due_10k=None,
            refresh_due_10q=None,
            new_filings=(),
        ),
        error=str(error),
    )


if __name__ == "__main__":
    raise SystemExit(main())
