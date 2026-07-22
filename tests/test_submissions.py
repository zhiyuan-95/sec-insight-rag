import json
from pathlib import Path
from typing import Any

import pytest

from src.ingestion import SecPayloadError
from src.ingestion.submissions import (
    build_submissions_url,
    discover_annual_inline_xbrl_filings,
    validate_submissions_payload,
)


class FakeSubmissionsClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_json(self, url: str) -> dict[str, Any]:
        self.calls.append(url)
        return self.responses[url]


def _filing_arrays(*rows: tuple[str, str, str, str, Any]) -> dict[str, list[Any]]:
    fields = ("accessionNumber", "filingDate", "form", "primaryDocument", "isInlineXBRL")
    return {field: [row[index] for row in rows] for index, field in enumerate(fields)}


def test_build_submissions_url_zero_pads_cik() -> None:
    assert build_submissions_url("320193") == "https://data.sec.gov/submissions/CIK0000320193.json"


def test_validate_submissions_payload_accepts_fixture() -> None:
    payload = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))

    validate_submissions_payload(payload)


def test_validate_submissions_payload_rejects_missing_recent_fields() -> None:
    payload = {"cik": "0000320193", "filings": {"recent": {"form": []}}}

    with pytest.raises(SecPayloadError):
        validate_submissions_payload(payload)


def test_discover_annual_inline_xbrl_filings_merges_recent_and_all_archives() -> None:
    main_url = build_submissions_url("320193")
    first_archive_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    second_archive_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-002.json"
    client = FakeSubmissionsClient(
        {
            main_url: {
                "cik": "0000320193",
                "filings": {
                    "recent": _filing_arrays(
                        ("0000320193-25-000001", "2025-10-31", "10-K", "aapl-2025.htm", 1),
                    ),
                    "files": [
                        {"name": "CIK0000320193-submissions-001.json"},
                        {"name": "CIK0000320193-submissions-002.json"},
                    ],
                },
            },
            first_archive_url: _filing_arrays(
                ("0000320193-23-000001", "2023-11-03", "10-K", "aapl-2023.htm", 1),
            ),
            second_archive_url: _filing_arrays(
                ("0000320193-24-000001", "2024-11-01", "10-K", "aapl-2024.htm", 1),
            ),
        }
    )

    filings = discover_annual_inline_xbrl_filings(client, "320193")

    assert [filing.accession_number for filing in filings] == [
        "0000320193-23-000001",
        "0000320193-24-000001",
        "0000320193-25-000001",
    ]
    assert client.calls == [main_url, first_archive_url, second_archive_url]


def test_discovery_deduplicates_before_selecting_annual_inline_filings() -> None:
    main_url = build_submissions_url("320193")
    archive_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    client = FakeSubmissionsClient(
        {
            main_url: {
                "cik": "0000320193",
                "filings": {
                    "recent": _filing_arrays(
                        ("duplicate", "2025-10-31", "10-K", "recent.htm", 0),
                        ("quarterly", "2025-08-01", "10-Q", "quarter.htm", 1),
                        ("amendment", "2025-11-07", "10-K/A", "amendment.htm", 1),
                    ),
                    "files": [{"name": "CIK0000320193-submissions-001.json"}],
                },
            },
            archive_url: _filing_arrays(
                ("duplicate", "2025-10-31", "10-K", "archive.htm", 1),
                ("annual", "2024-11-01", "10-K", "annual.htm", True),
            ),
        }
    )

    filings = discover_annual_inline_xbrl_filings(client, "320193")

    assert [(filing.accession_number, filing.form) for filing in filings] == [
        ("annual", "10-K"),
        ("amendment", "10-K/A"),
    ]


def test_discovery_rejects_missing_inline_xbrl_metadata() -> None:
    main_url = build_submissions_url("320193")
    client = FakeSubmissionsClient(
        {
            main_url: {
                "cik": "0000320193",
                "filings": {
                    "recent": {
                        "accessionNumber": ["annual"],
                        "filingDate": ["2025-10-31"],
                        "form": ["10-K"],
                        "primaryDocument": ["inline-looking-document.htm"],
                    },
                    "files": [],
                },
            }
        }
    )

    with pytest.raises(SecPayloadError, match="isInlineXBRL"):
        discover_annual_inline_xbrl_filings(client, "320193")


def test_discovery_rejects_invalid_inline_xbrl_metadata_without_guessing() -> None:
    main_url = build_submissions_url("320193")
    client = FakeSubmissionsClient(
        {
            main_url: {
                "cik": "0000320193",
                "filings": {
                    "recent": _filing_arrays(
                        ("annual", "2025-10-31", "10-K", "inline-looking-document.htm", "yes"),
                    ),
                    "files": [],
                },
            }
        }
    )

    with pytest.raises(SecPayloadError, match="isInlineXBRL"):
        discover_annual_inline_xbrl_filings(client, "320193")


def test_discovery_ignores_blank_documents_for_unselected_filings() -> None:
    main_url = build_submissions_url("320193")
    client = FakeSubmissionsClient(
        {
            main_url: {
                "cik": "0000320193",
                "filings": {
                    "recent": _filing_arrays(
                        ("old-annual", "2008-11-05", "10-K", "", 0),
                        ("quarterly", "2025-08-01", "10-Q", "", 0),
                        ("selected", "2025-10-31", "10-K", "annual.htm", 1),
                    ),
                    "files": [],
                },
            }
        }
    )

    filings = discover_annual_inline_xbrl_filings(client, "320193")

    assert [filing.accession_number for filing in filings] == ["selected"]
