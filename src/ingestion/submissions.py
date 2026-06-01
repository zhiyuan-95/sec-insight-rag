"""SEC company submissions retrieval."""

from __future__ import annotations

from typing import Any

from src.ingestion.errors import SecPayloadError
from src.ingestion.sec_client import SecClient
from src.ingestion.tickers import normalize_cik

SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"


def build_submissions_url(cik: str) -> str:
    """Build the SEC submissions URL for a CIK."""
    return SUBMISSIONS_URL_TEMPLATE.format(cik=normalize_cik(cik))


def get_company_submissions(client: SecClient, cik: str) -> dict[str, Any]:
    """Retrieve and validate SEC company submissions JSON."""
    url = build_submissions_url(cik)
    payload = client.get_json(url)
    validate_submissions_payload(payload)
    return payload


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
