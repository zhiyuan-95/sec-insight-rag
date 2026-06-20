import json
from pathlib import Path

import pytest

from src.ingestion import SecPayloadError, TickerNotFoundError
from src.ingestion.tickers import parse_ticker_mapping, resolve_ticker_to_cik


def test_parse_ticker_mapping_normalizes_ticker_and_cik() -> None:
    payload = json.loads(Path("data/fixtures/sec_company_tickers.json").read_text(encoding="utf-8"))

    mapping = parse_ticker_mapping(payload)

    assert mapping["AAPL"].cik == "0000320193"
    assert mapping["AAPL"].ticker == "AAPL"
    assert mapping["MSFT"].cik == "0000789019"


def test_resolve_ticker_to_cik_accepts_case_and_whitespace() -> None:
    payload = json.loads(Path("data/fixtures/sec_company_tickers.json").read_text(encoding="utf-8"))
    mapping = parse_ticker_mapping(payload)

    assert resolve_ticker_to_cik(" aapl ", mapping) == "0000320193"


def test_resolve_ticker_to_cik_rejects_unknown_ticker() -> None:
    payload = json.loads(Path("data/fixtures/sec_company_tickers.json").read_text(encoding="utf-8"))
    mapping = parse_ticker_mapping(payload)

    with pytest.raises(TickerNotFoundError):
        resolve_ticker_to_cik("NOPE", mapping)


def test_parse_ticker_mapping_rejects_malformed_cik() -> None:
    with pytest.raises(SecPayloadError):
        parse_ticker_mapping({"0": {"cik_str": "not-a-number", "ticker": "BAD", "title": "Bad Co"}})
