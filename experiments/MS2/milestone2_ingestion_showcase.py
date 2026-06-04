"""Milestone 2 experiment: SEC/XBRL ingestion and normalization showcase."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings, load_settings
from src.ingestion.companyfacts import build_companyfacts_url, get_companyfacts
from src.ingestion.errors import FilingNotFoundError, SecConfigurationError, SecIngestionError, TickerNotFoundError
from src.ingestion.filings import FilingMetadata, download_filing_document, require_latest_filings
from src.ingestion.sec_client import SecClient
from src.ingestion.submissions import build_submissions_url, get_company_submissions
from src.ingestion.tickers import COMPANY_TICKERS_URL, TickerMapping, load_ticker_mapping, resolve_ticker_to_cik
from src.processing import NormalizedFact, normalize_companyfacts
from src.storage import RawFactRepository, StoredRawFact, connect_sqlite
from main import FINANCIAL_STATEMENT_BY_CONCEPT, FINANCIAL_STATEMENT_ORDER

FIXTURE_DIR = PROJECT_ROOT / "data" / "fixtures"
DEFAULT_FIXTURE_WORK_DIR = PROJECT_ROOT / "data" / "exports" / "experiments" / "MS2"
SUPPORTED_FIXTURE_TICKERS = ("AAPL",)
FORM_ORDER = {"10-K": 0, "10-Q": 1}
PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class ExperimentResult:
    """Data collected for the printed Milestone 2 report."""

    mode: str
    ticker: str
    cik: str
    company_name: str
    database_path: Path
    filings_directory: Path
    filings: tuple[FilingMetadata, ...]
    downloaded_paths: tuple[Path, ...]
    normalized_facts: tuple[NormalizedFact, ...]
    stored_records: tuple[StoredRawFact, ...]
    upsert_attempt_count: int


class FixtureSecClient:
    """SEC-client-shaped fixture reader used by fixture mode."""

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.ticker_payload = _read_json(fixture_dir / "sec_company_tickers.json")
        self.submissions_payload = _read_json(fixture_dir / "sec_submissions_sample.json")
        self.companyfacts_payload = _read_json(fixture_dir / "sec_companyfacts_sample.json")

    def get_json(self, url: str) -> dict[str, Any]:
        """Return a saved fixture payload for the requested SEC URL."""
        if url == COMPANY_TICKERS_URL:
            return self.ticker_payload
        if url == build_submissions_url("0000320193"):
            return self.submissions_payload
        if url == build_companyfacts_url("0000320193"):
            return self.companyfacts_payload
        raise SecIngestionError(f"No fixture SEC JSON payload is available for URL: {url}")

    def get_bytes(self, url: str, *, accept: str = "*/*") -> bytes:
        """Return deterministic fixture filing HTML bytes."""
        return (
            "<html><body>"
            "<h1>Fixture SEC filing document</h1>"
            f"<p>source url: {url}</p>"
            "</body></html>"
        ).encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Milestone 2 showcase and print a human-inspection report."""
    args = _parse_args(argv)
    ticker = args.ticker.strip().upper()

    try:
        if args.mode == "fixture":
            result = _run_fixture_mode(ticker, args)
        else:
            result = _run_live_mode(ticker, args)
    except _UnsupportedFixtureTicker as exc:
        print(_format_unsupported_fixture_report(ticker, exc))
        return 1
    except (SecConfigurationError, SecIngestionError, TickerNotFoundError, FilingNotFoundError) as exc:
        print(_format_execution_error_report(ticker, args.mode, exc, args))
        return 1

    print(format_report(result))
    return 0


def format_report(result: ExperimentResult) -> str:
    """Format the Milestone 2 human-inspection report."""
    lines = [
        "Milestone 2 Experiment: SEC/XBRL Ingestion And Normalization",
        "",
        "Human Question:",
        "  If I ingest a company, can I inspect filing counts, filing locations,",
        "  normalized XBRL storage, and sample stored rows?",
        "",
        "Run Context:",
        f"  mode: {result.mode}",
        f"  ticker: {result.ticker}",
        f"  cik: {result.cik}",
        f"  database: {result.database_path}",
        f"  filings directory: {result.filings_directory}",
        "",
        "Company Resolution:",
    ]
    lines.extend(
        _format_table(
            ["ticker", "cik", "company name"],
            [[result.ticker, result.cik, result.company_name]],
        )
    )
    lines.extend(["", "Filing Period Coverage:"])
    lines.extend(_format_filing_period_coverage(result.filings, result.stored_records))
    lines.extend(["", "Selected Filings:"])
    lines.extend(_format_selected_filings(result.filings, result.stored_records))
    lines.extend(["", "Downloaded Filing Paths:"])
    lines.extend(_format_downloaded_paths(result.filings, result.downloaded_paths))
    lines.extend(["", "XBRL Normalization:"])
    lines.extend(_format_xbrl_summary(result))
    lines.extend(["", "XBRL Concepts Stored In Database:"])
    lines.extend(_format_xbrl_concepts(result.stored_records))
    lines.extend(["", "Top 5 raw_xbrl_facts Rows:"])
    lines.extend(_format_top_rows(_records_for_selected_filings(result.stored_records, result.filings)))
    lines.extend(
        [
            "",
            "Artifacts To Inspect:",
            f"  filing directory: {result.filings_directory}",
            "  database table: raw_xbrl_facts",
            "  source modules: src/ingestion/, src/processing/xbrl_normalizer.py,",
            "                  src/storage/facts_repository.py",
            "",
            "Expected Outcome:",
            "  The report should make it easy to inspect annual and quarterly filing",
            "  ingestion, downloaded filing locations, normalized XBRL storage, and stored",
            "  fact rows.",
            "",
            "Manual Judgment:",
            "  Compare the observed report with experiments/MS2/experiment_proposal.md.",
            "  The project owner decides whether the milestone behavior looks correct.",
        ]
    )
    return "\n".join(lines)


def _run_fixture_mode(ticker: str, args: argparse.Namespace) -> ExperimentResult:
    if ticker not in SUPPORTED_FIXTURE_TICKERS:
        raise _UnsupportedFixtureTicker(
            f"fixture mode supports only {', '.join(SUPPORTED_FIXTURE_TICKERS)}; "
            f"received {ticker}"
        )

    db_path = _fixture_db_path(args)
    filings_dir = _fixture_filings_dir(args)
    settings = Settings.model_validate(
        {
            "STOCK_SQL_DB_PATH": db_path,
            "STOCK_FILINGS_BASE_DIR": filings_dir,
        }
    )
    return _run_pipeline(
        mode="fixture",
        ticker=ticker,
        client=FixtureSecClient(FIXTURE_DIR),
        database_path=settings.stock_sql_db_path,
        filings_directory=settings.stock_filings_base_dir,
    )


def _run_live_mode(ticker: str, args: argparse.Namespace) -> ExperimentResult:
    settings = load_settings(args.env_file)
    db_path = Path(args.db_path) if args.db_path else settings.stock_sql_db_path
    filings_dir = Path(args.filings_dir) if args.filings_dir else settings.stock_filings_base_dir
    client = SecClient(settings.sec_user_agent)
    return _run_pipeline(
        mode="live",
        ticker=ticker,
        client=client,
        database_path=db_path,
        filings_directory=filings_dir,
    )


def _run_pipeline(
    *,
    mode: str,
    ticker: str,
    client: Any,
    database_path: Path,
    filings_directory: Path,
) -> ExperimentResult:
    ticker_mapping = load_ticker_mapping(client)
    cik = resolve_ticker_to_cik(ticker, ticker_mapping)
    ticker_entry = ticker_mapping[ticker]
    submissions = get_company_submissions(client, cik)
    companyfacts = get_companyfacts(client, cik)

    filings = tuple(_sort_filings(require_latest_filings(submissions, {"10-K", "10-Q"})))
    downloaded_paths = tuple(download_filing_document(client, filing, filings_directory) for filing in filings)
    normalized_facts = tuple(normalize_companyfacts(companyfacts))

    with connect_sqlite(database_path) as connection:
        repository = RawFactRepository(connection)
        repository.initialize()
        upsert_attempt_count = repository.upsert_facts(list(normalized_facts))
        stored_records = tuple(repository.list_fact_records(cik))

    return ExperimentResult(
        mode=mode,
        ticker=ticker,
        cik=cik,
        company_name=_company_name(companyfacts, submissions, ticker_entry),
        database_path=database_path,
        filings_directory=filings_directory,
        filings=filings,
        downloaded_paths=downloaded_paths,
        normalized_facts=normalized_facts,
        stored_records=stored_records,
        upsert_attempt_count=upsert_attempt_count,
    )


def _format_filing_period_coverage(
    filings: tuple[FilingMetadata, ...],
    records: tuple[StoredRawFact, ...],
) -> list[str]:
    rows: list[list[str]] = []
    facts = [record.fact for record in _records_for_selected_filings(records, filings)]
    for form in ("10-K", "10-Q"):
        form_filings = [filing for filing in filings if filing.form == form]
        periods = _periods_for_form(form, facts)
        unit = "fiscal year" if form == "10-K" else "fiscal quarter"
        rows.append(
            [
                form,
                _period_count_label(len(periods), unit),
                str(len(form_filings)),
                _format_list(periods),
            ]
        )
    return _format_table(["form", "periods represented", "filings selected", "periods"], rows)


def _format_selected_filings(
    filings: tuple[FilingMetadata, ...],
    records: tuple[StoredRawFact, ...],
) -> list[str]:
    facts = [record.fact for record in records]
    rows = [
        [
            filing.form,
            filing.filing_date,
            _report_date_for_filing(filing, facts),
            filing.accession_number,
            filing.primary_document,
        ]
        for filing in filings
    ]
    return _format_table(
        ["form", "filing date", "report date", "accession number", "primary document"],
        rows,
    )


def _format_downloaded_paths(
    filings: tuple[FilingMetadata, ...],
    downloaded_paths: tuple[Path, ...],
) -> list[str]:
    path_by_accession = {
        filing.accession_number: path
        for filing, path in zip(filings, downloaded_paths, strict=False)
    }
    rows = [
        [
            filing.form,
            str(path_by_accession.get(filing.accession_number, "not downloaded")),
        ]
        for filing in filings
    ]
    return _format_table(["form", "local path"], rows)


def _format_xbrl_summary(result: ExperimentResult) -> list[str]:
    distinct_concepts = {record.fact.concept for record in result.stored_records}
    flags = sorted({flag for fact in result.normalized_facts for flag in fact.quality_flags})
    return [
        "  normalized object: NormalizedFact",
        "  storage table: raw_xbrl_facts",
        "  taxonomy filter: us-gaap",
        "  concept filter: common us-gaap concept list",
        "  form filter: 10-K, 10-Q",
        f"  normalized fact count: {len(result.normalized_facts)}",
        f"  upsert attempted rows: {result.upsert_attempt_count}",
        f"  stored row count: {len(result.stored_records)}",
        f"  distinct concepts ingested: {len(distinct_concepts)}",
        f"  quality flags observed: {_format_list(flags)}",
    ]


def _format_xbrl_concepts(records: tuple[StoredRawFact, ...]) -> list[str]:
    if not records:
        return ["  No XBRL concepts are stored for this company."]

    stored_rows_by_concept: Counter[tuple[str, str]] = Counter()
    forms_by_concept: dict[tuple[str, str], set[str]] = defaultdict(set)
    units_by_concept: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        fact = record.fact
        key = (fact.taxonomy, fact.concept)
        stored_rows_by_concept[key] += 1
        if fact.form:
            forms_by_concept[key].add(fact.form)
        units_by_concept[key].add(fact.unit)

    rows_by_statement: dict[str, list[list[str]]] = defaultdict(list)
    for taxonomy, concept in sorted(stored_rows_by_concept):
        key = (taxonomy, concept)
        statement = FINANCIAL_STATEMENT_BY_CONCEPT.get(concept, "Unmapped financial facts")
        rows_by_statement[statement].append(
            [
                taxonomy,
                concept,
                str(stored_rows_by_concept[key]),
                _format_list(sorted(forms_by_concept[key])),
                _format_list(sorted(units_by_concept[key])),
            ]
        )

    lines: list[str] = []
    for statement in FINANCIAL_STATEMENT_ORDER:
        rows = rows_by_statement.get(statement, [])
        if not rows:
            continue
        lines.append(f"  {statement}:")
        lines.extend(
            f"  {line}"
            for line in _format_table(
                ["taxonomy", "concept", "stored rows", "forms", "units"],
                rows,
            )
        )
    return lines


def _format_top_rows(records: tuple[StoredRawFact, ...]) -> list[str]:
    if not records:
        return ["  No rows stored in raw_xbrl_facts."]

    rows = []
    for record in records[:5]:
        fact = record.fact
        rows.append(
            [
                str(record.raw_fact_id),
                fact.cik,
                fact.taxonomy,
                fact.concept,
                fact.unit,
                _optional_number(fact.fiscal_year),
                fact.fiscal_period or "",
                fact.form or "",
                str(fact.value) if fact.value is not None else "",
                _format_list(list(fact.quality_flags)),
            ]
        )
    return _format_table(
        [
            "id",
            "cik",
            "taxonomy",
            "concept",
            "unit",
            "fiscal_year",
            "fiscal_period",
            "form",
            "value",
            "quality_flags",
        ],
        rows,
    )


def _records_for_selected_filings(
    records: tuple[StoredRawFact, ...],
    filings: tuple[FilingMetadata, ...],
) -> tuple[StoredRawFact, ...]:
    selected_accessions = {filing.accession_number for filing in filings}
    return tuple(
        record
        for record in records
        if record.fact.accession_number in selected_accessions
    )


def _format_unsupported_fixture_report(ticker: str, error: Exception) -> str:
    lines = [
        "Milestone 2 Experiment: SEC/XBRL Ingestion And Normalization",
        "",
        "Human Question:",
        "  If I ingest a company, can I inspect filing counts, filing locations,",
        "  normalized XBRL storage, and sample stored rows?",
        "",
        "Run Context:",
        "  mode: fixture",
        f"  ticker: {ticker}",
        "",
        "Unsupported Fixture Ticker:",
        f"  {error}",
        "  no live SEC call was made",
        "",
        "Expected Outcome:",
        "  Fixture mode should clearly report when a requested ticker has no saved",
        "  fixture payload instead of pretending live data exists.",
        "",
        "Manual Judgment:",
        "  Confirm that fixture mode stayed offline and explained the unsupported case.",
    ]
    return "\n".join(lines)


def _format_execution_error_report(
    ticker: str,
    mode: str,
    error: Exception,
    args: argparse.Namespace,
) -> str:
    lines = [
        "Milestone 2 Experiment: SEC/XBRL Ingestion And Normalization",
        "",
        "Human Question:",
        "  If I ingest a company, can I inspect filing counts, filing locations,",
        "  normalized XBRL storage, and sample stored rows?",
        "",
        "Run Context:",
        f"  mode: {mode}",
        f"  ticker: {ticker}",
        f"  env file: {args.env_file}",
        "",
        "Execution Error:",
        f"  {error}",
        "",
        "Expected Outcome:",
        "  Configuration, SEC, fixture, or filing-selection problems should be printed",
        "  clearly so the project owner can see why the experiment could not run.",
        "",
        "Manual Judgment:",
        "  Fix the printed configuration or data issue, then run the experiment again.",
    ]
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a Milestone 2 SEC/XBRL ingestion and normalization showcase.",
    )
    parser.add_argument("--ticker", default="AAPL", help="Company ticker to ingest.")
    parser.add_argument(
        "--mode",
        choices=("fixture", "live"),
        default="fixture",
        help="Use saved fixtures or live SEC endpoints.",
    )
    parser.add_argument(
        "--env-file",
        default="config.env",
        help="Environment file used by live mode.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite path. Fixture mode defaults to data/exports/experiments/MS2/fixture.db.",
    )
    parser.add_argument(
        "--filings-dir",
        default=None,
        help="Optional filing output directory. Fixture mode defaults to data/exports/experiments/MS2/filings.",
    )
    return parser.parse_args(argv)


def _fixture_db_path(args: argparse.Namespace) -> Path:
    if args.db_path:
        return Path(args.db_path)
    return DEFAULT_FIXTURE_WORK_DIR / "milestone2_fixture.db"


def _fixture_filings_dir(args: argparse.Namespace) -> Path:
    if args.filings_dir:
        return Path(args.filings_dir)
    return DEFAULT_FIXTURE_WORK_DIR / "filings"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SecIngestionError(f"Fixture JSON was not an object: {path}")
    return payload


def _sort_filings(filings: list[FilingMetadata]) -> list[FilingMetadata]:
    return sorted(filings, key=lambda filing: (FORM_ORDER.get(filing.form, 99), filing.filing_date))


def _company_name(
    companyfacts: dict[str, Any],
    submissions: dict[str, Any],
    ticker_entry: TickerMapping,
) -> str:
    return (
        _optional_text(companyfacts.get("entityName"))
        or _optional_text(submissions.get("name"))
        or ticker_entry.title
    )


def _periods_for_form(form: str, facts: list[NormalizedFact]) -> list[str]:
    periods = {
        _format_period(fact.fiscal_year, fact.fiscal_period, fact.end_date.isoformat() if fact.end_date else "")
        for fact in facts
        if fact.form == form
    }
    return sorted(periods, key=_period_sort_key, reverse=True)


def _report_date_for_filing(filing: FilingMetadata, facts: list[NormalizedFact]) -> str:
    dates = [
        fact.end_date.isoformat()
        for fact in facts
        if fact.accession_number == filing.accession_number
        and fact.form == filing.form
        and fact.end_date is not None
    ]
    return max(dates) if dates else "unknown"


def _format_period(fiscal_year: int | None, fiscal_period: str | None, fallback: str) -> str:
    if fiscal_year is None:
        return fallback or "unknown"
    if fiscal_period and fiscal_period.upper() != "FY":
        return f"FY{fiscal_year} {fiscal_period.upper()}"
    return f"FY{fiscal_year}"


def _period_sort_key(period: str) -> tuple[int, int, str]:
    parts = period.replace("FY", "", 1).split()
    try:
        year = int(parts[0])
    except (IndexError, ValueError):
        return (0, 0, period)
    quarter = PERIOD_ORDER.get(parts[1] if len(parts) > 1 else "FY", 0)
    return (year, quarter, period)


def _period_count_label(count: int, unit: str) -> str:
    label = unit if count == 1 else f"{unit}s"
    return f"{count} {label}"


def _format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in string_rows))
        if string_rows
        else len(headers[index])
        for index in range(len(headers))
    ]
    lines = ["  " + "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    for row in string_rows:
        lines.append("  " + "  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))
    return lines


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: int | None) -> str:
    return str(value) if value is not None else ""


class _UnsupportedFixtureTicker(Exception):
    """Raised when fixture mode has no saved payload for the requested ticker."""


if __name__ == "__main__":
    raise SystemExit(main())
