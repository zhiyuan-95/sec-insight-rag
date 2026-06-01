"""SEC companyfacts retrieval."""

from __future__ import annotations

from typing import Any

from src.ingestion.errors import SecPayloadError
from src.ingestion.sec_client import SecClient
from src.ingestion.tickers import normalize_cik

COMPANYFACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def build_companyfacts_url(cik: str) -> str:
    """Build the SEC companyfacts URL for a CIK."""
    return COMPANYFACTS_URL_TEMPLATE.format(cik=normalize_cik(cik))


def get_companyfacts(client: SecClient, cik: str) -> dict[str, Any]:
    """Retrieve and validate SEC companyfacts JSON."""
    url = build_companyfacts_url(cik)
    payload = client.get_json(url)
    validate_companyfacts_payload(payload)
    return payload


def validate_companyfacts_payload(payload: dict[str, Any]) -> None:
    """Validate the minimum companyfacts shape needed for ingestion."""
    if "cik" not in payload:
        raise SecPayloadError("SEC companyfacts payload missing cik")
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise SecPayloadError("SEC companyfacts payload missing facts object")
