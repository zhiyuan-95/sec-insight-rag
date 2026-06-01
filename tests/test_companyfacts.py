import json
from pathlib import Path

import pytest

from src.ingestion import SecPayloadError
from src.ingestion.companyfacts import build_companyfacts_url, validate_companyfacts_payload


def test_build_companyfacts_url_zero_pads_cik() -> None:
    assert build_companyfacts_url("320193") == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"


def test_validate_companyfacts_payload_accepts_fixture() -> None:
    payload = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))

    validate_companyfacts_payload(payload)


def test_validate_companyfacts_payload_rejects_missing_facts() -> None:
    with pytest.raises(SecPayloadError):
        validate_companyfacts_payload({"cik": 320193})
