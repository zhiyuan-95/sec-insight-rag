"""SEC filing metadata and download helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ingestion.errors import FilingNotFoundError, SecPayloadError
from src.ingestion.sec_client import SecClient
from src.ingestion.tickers import normalize_cik

SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_FORMS = frozenset({"10-K", "10-Q"})


@dataclass(frozen=True)
class FilingMetadata:
    """Metadata for a downloadable SEC filing document."""

    cik: str
    accession_number: str
    form: str
    filing_date: str
    primary_document: str
    document_url: str


def list_recent_filings(submissions: dict[str, Any], forms: set[str] | frozenset[str]) -> list[FilingMetadata]:
    """Extract recent filing metadata for requested forms."""
    recent = _get_recent_filings(submissions)
    normalized_forms = {form.upper() for form in forms}
    lengths = _field_lengths(recent, ["accessionNumber", "filingDate", "form", "primaryDocument"])
    if len(set(lengths.values())) != 1:
        raise SecPayloadError("SEC recent filings arrays have inconsistent lengths")

    cik = normalize_cik(submissions.get("cik"))
    filings: list[FilingMetadata] = []
    for index in range(next(iter(lengths.values()), 0)):
        form = _read_recent_value(recent, "form", index).upper()
        if form not in normalized_forms:
            continue
        accession_number = _read_recent_value(recent, "accessionNumber", index)
        filing_date = _read_recent_value(recent, "filingDate", index)
        primary_document = _read_recent_value(recent, "primaryDocument", index)
        document_url = build_filing_document_url(cik, accession_number, primary_document)
        filings.append(
            FilingMetadata(
                cik=cik,
                accession_number=accession_number,
                form=form,
                filing_date=filing_date,
                primary_document=primary_document,
                document_url=document_url,
            )
        )
    return filings


def select_latest_filings(
    submissions: dict[str, Any],
    forms: set[str] | frozenset[str] = DEFAULT_FORMS,
) -> list[FilingMetadata]:
    """Return at most one latest filing for each requested form."""
    latest_by_form: dict[str, FilingMetadata] = {}
    requested = {form.upper() for form in forms}
    for filing in list_recent_filings(submissions, requested):
        if filing.form not in latest_by_form:
            latest_by_form[filing.form] = filing
    return [latest_by_form[form] for form in requested if form in latest_by_form]


def require_latest_filings(
    submissions: dict[str, Any],
    forms: set[str] | frozenset[str] = DEFAULT_FORMS,
) -> list[FilingMetadata]:
    """Return latest filings and fail if any requested form is absent."""
    requested = {form.upper() for form in forms}
    filings = select_latest_filings(submissions, requested)
    found = {filing.form for filing in filings}
    missing = sorted(requested - found)
    if missing:
        raise FilingNotFoundError(f"Missing requested filing forms: {', '.join(missing)}")
    return filings


def build_filing_document_url(cik: str, accession_number: str, primary_document: str) -> str:
    """Build the SEC archive URL for a filing document."""
    normalized_cik = str(int(normalize_cik(cik)))
    clean_accession = _validate_accession_number(accession_number).replace("-", "")
    clean_document = _validate_primary_document(primary_document)
    return f"{SEC_ARCHIVES_BASE_URL}/{normalized_cik}/{clean_accession}/{clean_document}"


def download_filing_document(client: SecClient, filing: FilingMetadata, base_dir: Path) -> Path:
    """Download a filing document below the configured base directory."""
    target_path = _build_local_filing_path(base_dir, filing)
    if target_path.exists():
        return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(client.get_bytes(filing.document_url, accept="text/html,application/xhtml+xml,*/*"))
    return target_path


def _build_local_filing_path(base_dir: Path, filing: FilingMetadata) -> Path:
    base = base_dir.resolve()
    target = (
        base
        / normalize_cik(filing.cik)
        / _validate_accession_number(filing.accession_number)
        / _validate_primary_document(filing.primary_document)
    ).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise SecPayloadError("Resolved filing path escaped the configured base directory") from exc
    return target


def _get_recent_filings(submissions: dict[str, Any]) -> dict[str, Any]:
    filings = submissions.get("filings")
    if not isinstance(filings, dict):
        raise SecPayloadError("SEC submissions payload missing filings object")
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise SecPayloadError("SEC submissions payload missing recent filings object")
    return recent


def _field_lengths(recent: dict[str, Any], fields: list[str]) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for field in fields:
        value = recent.get(field)
        if not isinstance(value, list):
            raise SecPayloadError(f"SEC recent filings field was not a list: {field}")
        lengths[field] = len(value)
    return lengths


def _read_recent_value(recent: dict[str, Any], field: str, index: int) -> str:
    value = recent[field][index]
    if value is None or not str(value).strip():
        raise SecPayloadError(f"SEC recent filings field had a blank value: {field}")
    return str(value).strip()


def _validate_accession_number(accession_number: str) -> str:
    value = accession_number.strip()
    if not value:
        raise SecPayloadError("Filing accession number cannot be blank")
    if "/" in value or "\\" in value or ".." in value:
        raise SecPayloadError("Filing accession number contains invalid path characters")
    return value


def _validate_primary_document(primary_document: str) -> str:
    value = primary_document.strip()
    if not value:
        raise SecPayloadError("Filing primary document cannot be blank")
    if "/" in value or "\\" in value or ".." in value:
        raise SecPayloadError("Filing primary document contains invalid path characters")
    return value
