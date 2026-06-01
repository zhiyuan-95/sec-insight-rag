import json
from pathlib import Path

import pytest

from src.config import Settings
from src.ingestion import CompanyIngestionResult, FilingMetadata, SecConfigurationError, TickerMapping, ingest_company
from src.ingestion import company as company_module
from src.storage import RawFactRepository, connect_sqlite


def _settings(tmp_path: Path, sec_user_agent: str | None = "Example contact@example.com") -> Settings:
    return Settings(
        sec_user_agent=sec_user_agent,
        stock_sql_db_path=tmp_path / "stock.db",
        stock_filings_base_dir=tmp_path / "filings",
    )


def test_ingest_company_orchestrates_sec_processing_and_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))
    companyfacts = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))
    call_order: list[str] = []

    def load_ticker_mapping(client) -> dict[str, TickerMapping]:
        call_order.append("load_ticker_mapping")
        return {"AAPL": TickerMapping(ticker="AAPL", cik="0000320193", title="Apple Inc.")}

    def get_company_submissions(client, cik: str) -> dict:
        call_order.append("get_company_submissions")
        assert cik == "0000320193"
        return submissions

    def get_companyfacts(client, cik: str) -> dict:
        call_order.append("get_companyfacts")
        assert cik == "0000320193"
        return companyfacts

    def download_filing_document(client, filing: FilingMetadata, base_dir: Path) -> Path:
        call_order.append(f"download:{filing.form}")
        path = base_dir / filing.cik / filing.accession_number / filing.primary_document
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>filing</html>", encoding="utf-8")
        return path

    monkeypatch.setattr(company_module, "load_ticker_mapping", load_ticker_mapping)
    monkeypatch.setattr(company_module, "get_company_submissions", get_company_submissions)
    monkeypatch.setattr(company_module, "get_companyfacts", get_companyfacts)
    monkeypatch.setattr(company_module, "download_filing_document", download_filing_document)

    result = ingest_company(" aapl ", _settings(tmp_path))

    assert isinstance(result, CompanyIngestionResult)
    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert {filing.form for filing in result.filings} == {"10-K", "10-Q"}
    assert len(result.downloaded_filings) == 2
    assert result.normalized_fact_count == 5
    assert result.stored_fact_count == 5
    assert result.warnings == (
        "Normalized facts include quality flag: ambiguous_unit",
        "Normalized facts include quality flag: duplicate_fact",
    )
    assert call_order[:3] == [
        "load_ticker_mapping",
        "get_company_submissions",
        "get_companyfacts",
    ]

    with connect_sqlite(tmp_path / "stock.db") as connection:
        stored = RawFactRepository(connection).list_facts("0000320193")

    assert len(stored) == 4
    assert {fact.concept for fact in stored} == {"Assets", "Revenues"}


def test_ingest_company_rejects_missing_sec_user_agent(tmp_path: Path) -> None:
    with pytest.raises(SecConfigurationError):
        ingest_company("AAPL", _settings(tmp_path, sec_user_agent=None))
