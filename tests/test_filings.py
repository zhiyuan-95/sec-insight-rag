import json
from pathlib import Path

import pytest

from src.ingestion import FilingNotFoundError, SecPayloadError
from src.ingestion.filings import (
    FilingMetadata,
    build_filing_document_url,
    download_filing_document,
    list_recent_filings,
    require_latest_filings,
    select_latest_filings,
)


class FakeDownloadClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_bytes(self, url: str, *, accept: str = "*/*") -> bytes:
        self.calls.append((url, accept))
        return b"<html>filing</html>"


def _submissions_fixture() -> dict:
    return json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))


def test_list_recent_filings_extracts_requested_forms() -> None:
    filings = list_recent_filings(_submissions_fixture(), {"10-K", "10-Q"})

    assert [filing.form for filing in filings] == ["10-K", "10-Q"]
    assert filings[0].cik == "0000320193"
    assert filings[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019325000079/aapl-20250927.htm"
    )


def test_select_latest_filings_returns_one_per_form() -> None:
    filings = select_latest_filings(_submissions_fixture(), {"10-K", "10-Q"})

    assert {filing.form for filing in filings} == {"10-K", "10-Q"}
    assert {filing.accession_number for filing in filings} == {
        "0000320193-25-000079",
        "0000320193-25-000073",
    }


def test_require_latest_filings_raises_for_missing_form() -> None:
    with pytest.raises(FilingNotFoundError):
        require_latest_filings(_submissions_fixture(), {"10-K", "S-1"})


def test_build_filing_document_url_uses_integer_cik_and_dashless_accession() -> None:
    assert build_filing_document_url(
        "0000320193",
        "0000320193-25-000079",
        "aapl-20250927.htm",
    ) == "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"


def test_list_recent_filings_rejects_inconsistent_recent_arrays() -> None:
    payload = _submissions_fixture()
    payload["filings"]["recent"]["primaryDocument"] = []

    with pytest.raises(SecPayloadError):
        list_recent_filings(payload, {"10-K"})


def test_download_filing_document_writes_below_base_dir(tmp_path: Path) -> None:
    filing = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        form="10-K",
        filing_date="2025-10-31",
        primary_document="aapl-20250927.htm",
        document_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    )
    client = FakeDownloadClient()

    path = download_filing_document(client, filing, tmp_path)

    assert path == tmp_path / "0000320193" / "0000320193-25-000079" / "aapl-20250927.htm"
    assert path.read_bytes() == b"<html>filing</html>"
    assert client.calls == [(filing.document_url, "text/html,application/xhtml+xml,*/*")]


def test_download_filing_document_reuses_existing_file(tmp_path: Path) -> None:
    filing = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        form="10-K",
        filing_date="2025-10-31",
        primary_document="aapl-20250927.htm",
        document_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    )
    existing_path = tmp_path / "0000320193" / "0000320193-25-000079" / "aapl-20250927.htm"
    existing_path.parent.mkdir(parents=True)
    existing_path.write_bytes(b"existing")
    client = FakeDownloadClient()

    path = download_filing_document(client, filing, tmp_path)

    assert path == existing_path
    assert path.read_bytes() == b"existing"
    assert client.calls == []
