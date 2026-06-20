import json
from pathlib import Path

import pytest

from src.ingestion import SecPayloadError
from src.ingestion.submissions import build_submissions_url, validate_submissions_payload


def test_build_submissions_url_zero_pads_cik() -> None:
    assert build_submissions_url("320193") == "https://data.sec.gov/submissions/CIK0000320193.json"


def test_validate_submissions_payload_accepts_fixture() -> None:
    payload = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))

    validate_submissions_payload(payload)


def test_validate_submissions_payload_rejects_missing_recent_fields() -> None:
    payload = {"cik": "0000320193", "filings": {"recent": {"form": []}}}

    with pytest.raises(SecPayloadError):
        validate_submissions_payload(payload)
