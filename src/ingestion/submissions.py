"""SEC company submissions retrieval."""

from __future__ import annotations

from typing import Any

from src.ingestion.errors import SecPayloadError
from src.ingestion.filings import (
    FilingMetadata,
    build_filing_document_url,
    read_required_filing_text,
    validate_parallel_filing_arrays,
)
from src.ingestion.sec_client import SecClient
from src.ingestion.tickers import normalize_cik

SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_FILE_URL_TEMPLATE = "https://data.sec.gov/submissions/{name}"
ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
DISCOVERY_FIELDS = (
    "accessionNumber",
    "filingDate",
    "form",
    "primaryDocument",
    "isInlineXBRL",
)


def build_submissions_url(cik: str) -> str:
    """Build the SEC submissions URL for a CIK."""
    return SUBMISSIONS_URL_TEMPLATE.format(cik=normalize_cik(cik))


def get_company_submissions(client: SecClient, cik: str) -> dict[str, Any]:
    """Retrieve and validate SEC company submissions JSON."""
    url = build_submissions_url(cik)
    payload = client.get_json(url)
    validate_submissions_payload(payload)
    return payload


def discover_annual_inline_xbrl_filings(client: SecClient, cik: str) -> list[FilingMetadata]:
    """Return the complete selected annual Inline XBRL filing inventory."""
    submissions = get_company_submissions(client, cik)
    normalized_cik = normalize_cik(submissions["cik"])
    filings = submissions["filings"]
    sources = [filings["recent"]]

    file_references = filings.get("files", [])
    if not isinstance(file_references, list):
        raise SecPayloadError("SEC submissions filings files field was not a list")
    for reference in file_references:
        sources.append(client.get_json(_build_submissions_file_url(reference)))

    inventory_by_accession: dict[str, FilingMetadata] = {}
    seen_accessions: set[str] = set()
    for source in sources:
        for row in _read_filing_rows(source):
            is_inline_xbrl = _read_inline_xbrl_flag(row["isInlineXBRL"])
            accession_number = _read_required_history_text(row, "accessionNumber")
            if accession_number in seen_accessions:
                continue
            seen_accessions.add(accession_number)
            form = _read_required_history_text(row, "form").upper()
            if form not in ANNUAL_FORMS or not is_inline_xbrl:
                continue
            filing_date = _read_required_history_text(row, "filingDate")
            primary_document = _read_required_history_text(row, "primaryDocument")
            inventory_by_accession[accession_number] = FilingMetadata(
                cik=normalized_cik,
                accession_number=accession_number,
                form=form,
                filing_date=filing_date,
                primary_document=primary_document,
                document_url=build_filing_document_url(
                    normalized_cik,
                    accession_number,
                    primary_document,
                ),
            )

    return sorted(
        inventory_by_accession.values(),
        key=lambda filing: (filing.filing_date, filing.accession_number),
    )


def validate_submissions_payload(payload: dict[str, Any]) -> None:
    """Validate the minimum submissions shape needed for ingestion."""
    if "cik" not in payload:
        raise SecPayloadError("SEC submissions payload missing cik")
    filings = payload.get("filings")
    if not isinstance(filings, dict):
        raise SecPayloadError("SEC submissions payload missing filings object")
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        raise SecPayloadError("SEC submissions payload missing recent filings object")

    required_fields = {"accessionNumber", "filingDate", "form", "primaryDocument"}
    missing = sorted(field for field in required_fields if field not in recent)
    if missing:
        raise SecPayloadError(f"SEC submissions recent filings missing fields: {', '.join(missing)}")


def _build_submissions_file_url(reference: Any) -> str:
    if not isinstance(reference, dict):
        raise SecPayloadError("SEC submissions history file reference was not an object")
    name = reference.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SecPayloadError("SEC submissions history file reference missing name")
    clean_name = name.strip()
    if "/" in clean_name or "\\" in clean_name or ".." in clean_name:
        raise SecPayloadError("SEC submissions history file name contains invalid path characters")
    return SUBMISSIONS_FILE_URL_TEMPLATE.format(name=clean_name)


def _read_filing_rows(source: Any) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        raise SecPayloadError("SEC submissions filing history was not an object")
    row_count = validate_parallel_filing_arrays(
        source,
        DISCOVERY_FIELDS,
        context="SEC submissions filing history",
    )

    return [
        {field: source[field][index] for field in DISCOVERY_FIELDS}
        for index in range(row_count)
    ]


def _read_required_history_text(row: dict[str, Any], field: str) -> str:
    return read_required_filing_text(
        row[field],
        field=field,
        context="SEC submissions filing history",
    )


def _read_inline_xbrl_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise SecPayloadError("SEC submissions isInlineXBRL value must be true/false or 1/0")
