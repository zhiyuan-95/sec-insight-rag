"""Manual examination harness for the Plan 2.5 company ingestion workflow."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
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
from src.storage import CompanyRepository, connect_sqlite, initialize_database

EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "MS2_5"
DEFAULT_DB_PATH = EXPERIMENT_DIR / "experiment.db"
DEFAULT_REPORT_PATH = EXPERIMENT_DIR / "experiment_report.md"
DEFAULT_FILINGS_DIR = EXPERIMENT_DIR / "filings"
DEFAULT_EXPORTS_DIR = PROJECT_ROOT / "data" / "exports" / "ms2_5"
FORMS = ("10-K", "10-Q")


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
    paths = _paths_from_args(args)
    ticker = args.ticker.strip().upper()

    try:
        settings = _experiment_settings(args.env_file, paths)
        if not settings.sec_user_agent:
            raise SecConfigurationError("SEC_USER_AGENT is required for live SEC experiment runs")
        run = run_experiment(ticker=ticker, settings=settings, paths=paths)
    except (SecConfigurationError, SecIngestionError, TickerNotFoundError, FilingNotFoundError, ValueError) as exc:
        run = _error_run(ticker=ticker, paths=paths, error=exc)
        _present_report(run, write_report=args.write_report, full_report=args.full_report)
        return 1

    export_warnings = _export_csv_artifacts(paths)
    if export_warnings:
        run = replace(run, warnings=tuple(dict.fromkeys([*run.warnings, *export_warnings])))
    _present_report(run, write_report=args.write_report, full_report=args.full_report)
    return 0


def run_experiment(
    *,
    ticker: str,
    settings: Settings,
    paths: ExperimentPaths,
) -> ExperimentRun:
    """Run setup ingestion, then inspect the already-ingested session path."""
    _reset_database(paths.database)
    run_timestamp = datetime.now(timezone.utc).isoformat()
    normalized_ticker = _normalize_ticker(ticker)

    company_existed_before_setup = _company_exists(paths.database, normalized_ticker)
    setup_result = ingest_company(normalized_ticker, settings)
    setup_snapshot = _snapshot(paths.database, normalized_ticker)

    session_before_snapshot = _snapshot(paths.database, normalized_ticker)
    session_company_exists = _company_exists(paths.database, normalized_ticker)
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
        help="Write the detailed Markdown report to experiment_report.md while still printing the compact summary.",
    )
    parser.add_argument(
        "--full-report",
        action="store_true",
        help="Print the detailed Markdown report with compact table samples instead of the default summary.",
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


def _reset_database(database: Path) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()


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
        return {
            "company": company,
            "counts": _table_counts(connection),
            "filings": _filing_rows(connection, company_id),
            "filings_by_form": _accessions_by_form(connection, company_id),
            "active_filings_by_form": _active_filing_counts_by_form(connection, company_id),
            "metric_counts_by_statement": _metric_counts_by_statement(connection, company_id),
            "metric_sample": _metric_sample(connection, company_id),
            "traceability_sample": _traceability_sample(connection, company_id),
            "quality_flags": _quality_flags(connection, company.get("cik") if company else None),
        }


def _empty_snapshot() -> dict[str, Any]:
    return {
        "company": {},
        "counts": {"companies": 0, "filings": 0, "raw_xbrl_facts": 0, "financial_metrics": 0},
        "filings": [],
        "filings_by_form": {form_type: () for form_type in FORMS},
        "active_filings_by_form": {form_type: 0 for form_type in FORMS},
        "metric_counts_by_statement": [],
        "metric_sample": [],
        "traceability_sample": [],
        "quality_flags": (),
    }


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


def _write_report(run: ExperimentRun) -> None:
    run.paths.report.parent.mkdir(parents=True, exist_ok=True)
    run.paths.report.write_text(format_report(run, report_output="file"), encoding="utf-8")


def format_report(run: ExperimentRun, *, report_output: str = "terminal") -> str:
    """Render a compact Markdown report for manual inspection."""
    report_path: object = run.paths.report if report_output == "file" else "not written; terminal output only"
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
                "report": report_path,
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

    lines.extend(
        [
            "",
            "## Full Evidence Artifacts",
            "",
        ]
    )
    lines.extend(
        _definition_list(
            {
                "SQLite database": run.paths.database,
                "companies CSV": run.paths.exports_dir / "companies.csv",
                "filings CSV": run.paths.exports_dir / "filings.csv",
                "raw facts CSV": run.paths.exports_dir / "raw_xbrl_facts.csv",
                "financial metrics CSV": run.paths.exports_dir / "financial_metrics.csv",
                "traceability sample CSV": run.paths.exports_dir / "metric_traceability_sample.csv",
            }
        )
    )
    lines.extend(
        [
            "",
            "## Manual Judgment",
            "",
            "This report presents evidence only. Review the report, database, and CSVs to",
            "decide whether the observed behavior matches the Milestone 2.5 design.",
            "",
        ]
    )
    return "\n".join(lines)


def format_compact_report(run: ExperimentRun, *, report_written: bool = False) -> str:
    """Render a concise terminal report for quick manual inspection."""
    setup_company = run.setup_snapshot.get("company") or {}
    session_after_company = run.session_after_snapshot.get("company") or {}
    lines = [
        "Milestone 2.5 Plan 2.5 Ingestion Examination",
        "",
        "Run Context",
        f"  ticker: {run.ticker}",
        f"  run timestamp: {run.run_timestamp}",
        "  mode: live SEC, isolated experiment storage",
        f"  SEC_USER_AGENT configured: {_yes_no(run.sec_user_agent_configured)}",
        f"  report output: {'saved Markdown + compact terminal summary' if report_written else 'compact terminal summary'}",
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
    lines.extend(
        [
            f"  next 10-K check date after session: {session_after_company.get('next_check_date_10k') or 'not available'}",
            f"  next 10-Q check date after session: {session_after_company.get('next_check_date_10q') or 'not available'}",
            "",
            "Stored Rows After Session",
        ]
    )
    lines.extend(_compact_counts(run.session_after_snapshot, indent="  "))
    lines.extend(["", "Active Window After Session"])
    lines.extend(_compact_active_window(run.session_after_snapshot, indent="  "))
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
            "Full Evidence",
            f"  SQLite database: {run.paths.database}",
            f"  CSV exports: {run.paths.exports_dir}",
            f"  filing downloads: {run.paths.filings_dir}",
            f"  saved Markdown report: {run.paths.report if report_written else 'not written'}",
            "",
            "Manual Judgment",
            "  Review the compact summary, SQLite database, and CSVs to decide whether",
            "  the observed behavior matches the Milestone 2.5 design.",
            "",
            "More Detail",
            "  Add --full-report to print compact table samples in Markdown.",
            "  Add --write-report to save the detailed Markdown report file.",
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
        {"field": "SEC result", "value": _status_summary(decision)},
        {
            "field": "next 10-K check date after session",
            "value": after_company.get("next_check_date_10k") or "not available",
        },
        {
            "field": "next 10-Q check date after session",
            "value": after_company.get("next_check_date_10q") or "not available",
        },
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
    if write_report:
        _write_report(run)
    if full_report:
        print(format_report(run))
        return
    print(format_compact_report(run, report_written=write_report))


def _compact_counts(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    counts = snapshot.get("counts") or {}
    return [f"{indent}{table}: {count}" for table, count in counts.items()]


def _compact_active_window(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    active = snapshot.get("active_filings_by_form") or {}
    accessions = snapshot.get("filings_by_form") or {}
    return [
        f"{indent}{form_type}: {active.get(form_type, 0)} active filings; "
        f"{len(accessions.get(form_type, ()))} local accessions"
        for form_type in FORMS
    ]


def _compact_metric_counts(snapshot: dict[str, Any], *, indent: str) -> list[str]:
    rows = snapshot.get("metric_counts_by_statement") or []
    if not rows:
        return [f"{indent}none"]
    return [
        f"{indent}{row['statement_type']}: {row['total_metrics']} total, {row['active_metrics']} active"
        for row in rows
    ]


def _snapshot_sections(snapshot: dict[str, Any]) -> list[str]:
    lines: list[str] = ["", "### Company State", ""]
    lines.extend(_markdown_table([snapshot["company"]] if snapshot["company"] else []))
    lines.extend(["", "### Filing Inventory", ""])
    lines.extend(_markdown_table(snapshot["filings"][:8]))
    lines.extend(["", "### Raw Fact And Metric Counts", ""])
    lines.extend(_count_table(snapshot))
    lines.extend(["", "### Active Window", ""])
    lines.extend(_active_window_lines(snapshot))
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


def _export_csv_artifacts(paths: ExperimentPaths) -> tuple[str, ...]:
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
                _traceability_sample(connection, _first_company_id(connection)),
                paths.exports_dir / "metric_traceability_sample.csv",
            )
        except OSError as exc:
            warnings.append(f"CSV export skipped for metric_traceability_sample: {exc}")
    return tuple(warnings)


def _export_query(connection: sqlite3.Connection, query: str, path: Path) -> None:
    rows = _fetch_all(connection, query)
    _export_rows(rows, path)


def _export_rows(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if headers:
            writer.writeheader()
            writer.writerows(rows)


def _first_company_id(connection: sqlite3.Connection) -> int | None:
    row = connection.execute("SELECT company_id FROM companies ORDER BY company_id LIMIT 1").fetchone()
    return int(row["company_id"]) if row is not None else None


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
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(row.get(header)) for header in headers) + " |")
    return lines


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = text.replace("|", "/")
    if len(text) > 120:
        return text[:117] + "..."
    return text


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
