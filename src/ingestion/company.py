"""Company-level ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import Settings
from src.ingestion.companyfacts import get_companyfacts
from src.ingestion.filings import FilingMetadata, require_latest_filings, download_filing_document
from src.ingestion.sec_client import SecClient
from src.ingestion.submissions import get_company_submissions
from src.ingestion.tickers import load_ticker_mapping, resolve_ticker_to_cik
from src.processing import NormalizedFact, normalize_companyfacts
from src.storage import RawFactRepository, connect_sqlite


@dataclass(frozen=True)
class CompanyIngestionResult:
    """Result summary for one company ingestion run."""

    ticker: str
    cik: str
    filings: tuple[FilingMetadata, ...]
    downloaded_filings: tuple[Path, ...]
    normalized_fact_count: int
    stored_fact_count: int
    warnings: tuple[str, ...] = ()


def ingest_company(ticker: str, settings: Settings) -> CompanyIngestionResult:
    """Ingest one company from SEC data into local storage."""
    client = SecClient(settings.sec_user_agent)

    ticker_mapping = load_ticker_mapping(client)
    normalized_ticker = ticker.strip().upper()
    cik = resolve_ticker_to_cik(normalized_ticker, ticker_mapping)

    submissions = get_company_submissions(client, cik)
    companyfacts = get_companyfacts(client, cik)

    filings = tuple(require_latest_filings(submissions, {"10-K", "10-Q"}))
    downloaded_filings = tuple(
        download_filing_document(client, filing, settings.stock_filings_base_dir)
        for filing in filings
    )

    normalized_facts = normalize_companyfacts(companyfacts)
    warnings = _collect_quality_warnings(normalized_facts)

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        repository = RawFactRepository(connection)
        repository.initialize()
        stored_fact_count = repository.upsert_facts(normalized_facts)

    return CompanyIngestionResult(
        ticker=normalized_ticker,
        cik=cik,
        filings=filings,
        downloaded_filings=downloaded_filings,
        normalized_fact_count=len(normalized_facts),
        stored_fact_count=stored_fact_count,
        warnings=warnings,
    )


def _collect_quality_warnings(normalized_facts: list[NormalizedFact]) -> tuple[str, ...]:
    flags = sorted({flag for fact in normalized_facts for flag in fact.quality_flags})
    return tuple(f"Normalized facts include quality flag: {flag}" for flag in flags)
