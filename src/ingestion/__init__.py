"""SEC ingestion package."""

from src.ingestion.company import CompanyDeletionResult, CompanyIngestionResult, delete_ingested_company, ingest_company
from src.ingestion.companyfacts import build_companyfacts_url, get_companyfacts
from src.ingestion.errors import (
    FilingNotFoundError,
    SecConfigurationError,
    SecHttpError,
    SecIngestionError,
    SecJsonError,
    SecPayloadError,
    TickerNotFoundError,
)
from src.ingestion.filings import (
    FilingMetadata,
    build_filing_document_url,
    download_filing_document,
    list_recent_filings,
    require_latest_filings,
    select_latest_filings,
)
from src.ingestion.inline_xbrl import get_inline_xbrl_facts
from src.ingestion.sec_client import SecClient
from src.ingestion.submissions import (
    build_submissions_url,
    discover_annual_inline_xbrl_filings,
    get_company_submissions,
)
from src.ingestion.tickers import TickerMapping, load_ticker_mapping, resolve_ticker_to_cik

__all__ = [
    "FilingMetadata",
    "FilingNotFoundError",
    "CompanyDeletionResult",
    "CompanyIngestionResult",
    "SecClient",
    "SecConfigurationError",
    "SecHttpError",
    "SecIngestionError",
    "SecJsonError",
    "SecPayloadError",
    "TickerMapping",
    "TickerNotFoundError",
    "build_companyfacts_url",
    "build_filing_document_url",
    "build_submissions_url",
    "download_filing_document",
    "delete_ingested_company",
    "discover_annual_inline_xbrl_filings",
    "get_company_submissions",
    "get_companyfacts",
    "get_inline_xbrl_facts",
    "ingest_company",
    "list_recent_filings",
    "load_ticker_mapping",
    "require_latest_filings",
    "resolve_ticker_to_cik",
    "select_latest_filings",
]
