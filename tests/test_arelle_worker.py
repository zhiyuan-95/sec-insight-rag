from __future__ import annotations

import time
from dataclasses import replace
from multiprocessing.connection import Connection

from src.ingestion.arelle_worker import process_arelle_filing
from src.processing.arelle_codec import encode_arelle_result
from src.processing.arelle_records import (
    ArelleFilingRequest,
    ArelleResourceLimits,
    failed_arelle_result,
)


def _request(*, timeout_seconds: float = 10.0) -> ArelleFilingRequest:
    return ArelleFilingRequest(
        entry_document="C:/proof/filing.htm",
        package_manifest="C:/proof/manifest.json",
        cik="0000789019",
        accession_number="0001193125-25-256321",
        form="10-K",
        filing_date="2025-07-30",
        fiscal_year=2025,
        fiscal_period="FY",
        sec_user_agent="Example Agent contact@example.com",
        cache_directory="C:/proof/cache",
        limits=replace(
            ArelleResourceLimits(),
            total_timeout_seconds=timeout_seconds,
            max_serialized_bytes=100_000,
        ),
    )


def _send_result_worker(request: ArelleFilingRequest, connection: Connection) -> None:
    result = failed_arelle_result(
        request.accession_number,
        code="proof",
        message="bounded result",
    )
    connection.send_bytes(
        encode_arelle_result(result, max_bytes=request.limits.max_serialized_bytes)
    )
    connection.close()


def _send_invalid_worker(_request: ArelleFilingRequest, connection: Connection) -> None:
    connection.send_bytes(b"not-json")
    connection.close()


def _slow_worker(_request: ArelleFilingRequest, connection: Connection) -> None:
    time.sleep(2)
    connection.close()


def test_process_arelle_filing_receives_one_bounded_result() -> None:
    result = process_arelle_filing(_request(), worker_target=_send_result_worker)

    assert result.status == "failed"
    assert result.diagnostics[0].code == "proof"


def test_process_arelle_filing_rejects_malformed_worker_payload() -> None:
    result = process_arelle_filing(_request(), worker_target=_send_invalid_worker)

    assert result.status == "failed"
    assert result.diagnostics[0].code == "worker_payload_invalid"


def test_process_arelle_filing_terminates_worker_at_total_deadline() -> None:
    result = process_arelle_filing(
        _request(timeout_seconds=0.1),
        worker_target=_slow_worker,
    )

    assert result.status == "failed"
    assert result.diagnostics[0].code == "worker_timeout"
