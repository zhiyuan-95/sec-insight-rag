"""Ticker-to-CIK lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.ingestion.errors import SecPayloadError, TickerNotFoundError
from src.ingestion.sec_client import SecClient

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass(frozen=True)
class TickerMapping:
    """SEC ticker mapping entry."""

    ticker: str
    cik: str
    title: str


def load_ticker_mapping(client: SecClient) -> dict[str, TickerMapping]:
    """Load SEC ticker mappings keyed by uppercase ticker."""
    return parse_ticker_mapping(client.get_json(COMPANY_TICKERS_URL))


def parse_ticker_mapping(payload: dict[str, Any]) -> dict[str, TickerMapping]:
    """Parse SEC company_tickers.json payload."""
    mappings: dict[str, TickerMapping] = {}
    for raw_entry in payload.values():
        if not isinstance(raw_entry, dict):
            raise SecPayloadError("SEC ticker mapping entry was not an object")
        raw_ticker = raw_entry.get("ticker")
        raw_cik = raw_entry.get("cik_str")
        raw_title = raw_entry.get("title")
        if raw_ticker is None or raw_cik is None or raw_title is None:
            raise SecPayloadError("SEC ticker mapping entry missing ticker, cik_str, or title")

        ticker = str(raw_ticker).strip().upper()
        if not ticker:
            raise SecPayloadError("SEC ticker mapping entry had a blank ticker")
        cik = normalize_cik(raw_cik)
        mappings[ticker] = TickerMapping(ticker=ticker, cik=cik, title=str(raw_title).strip())

    return mappings


def resolve_ticker_to_cik(ticker: str, mapping: dict[str, TickerMapping]) -> str:
    """Resolve a user ticker to a zero-padded 10-digit CIK."""
    normalized = ticker.strip().upper()
    if not normalized:
        raise TickerNotFoundError("Ticker cannot be blank")
    try:
        return mapping[normalized].cik
    except KeyError as exc:
        raise TickerNotFoundError(f"Ticker not found in SEC mapping: {normalized}") from exc


def normalize_cik(value: Any) -> str:
    """Normalize SEC CIK values to 10 digits."""
    text = str(value).strip()
    if not text.isdigit():
        raise SecPayloadError(f"CIK must be numeric: {text}")
    if len(text) > 10:
        raise SecPayloadError(f"CIK is longer than 10 digits: {text}")
    return text.zfill(10)
