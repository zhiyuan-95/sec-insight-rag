"""One-process-per-accession execution boundary for canonical Arelle loads."""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection

from src.ingestion.arelle_adapter import load_arelle_filing
from src.processing.arelle_codec import decode_arelle_result, encode_arelle_result
from src.processing.arelle_records import (
    ArelleFilingRequest,
    ArelleFilingResult,
    failed_arelle_result,
)


WorkerTarget = Callable[[ArelleFilingRequest, Connection], None]


def process_arelle_filing(
    request: ArelleFilingRequest,
    *,
    worker_target: WorkerTarget | None = None,
) -> ArelleFilingResult:
    """Run one accession in an isolated process with a hard total deadline."""
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=worker_target or _worker_main,
        args=(request, send_connection),
        name=f"arelle-{request.accession_number}",
    )
    process.start()
    send_connection.close()
    try:
        if not receive_connection.poll(request.limits.total_timeout_seconds):
            _terminate_process(process)
            return failed_arelle_result(
                request.accession_number,
                code="worker_timeout",
                message=(
                    "Arelle worker exceeded "
                    f"{request.limits.total_timeout_seconds} seconds"
                ),
            )
        try:
            payload = receive_connection.recv_bytes(request.limits.max_serialized_bytes)
        except OSError:
            _terminate_process(process)
            return failed_arelle_result(
                request.accession_number,
                code="worker_payload_oversized",
                message="Arelle worker payload exceeded the configured byte limit",
            )
        except EOFError:
            _terminate_process(process)
            return failed_arelle_result(
                request.accession_number,
                code="worker_no_payload",
                message="Arelle worker exited without a result payload",
            )
        process.join(timeout=1.0)
        if process.is_alive():
            _terminate_process(process)
        try:
            return decode_arelle_result(
                payload,
                max_bytes=request.limits.max_serialized_bytes,
                expected_accession_number=request.accession_number,
            )
        except Exception as exc:
            return failed_arelle_result(
                request.accession_number,
                code="worker_payload_invalid",
                message=str(exc),
            )
    finally:
        receive_connection.close()
        if process.is_alive():
            _terminate_process(process)
        process.close()


def _worker_main(request: ArelleFilingRequest, connection: Connection) -> None:
    try:
        result = load_arelle_filing(request)
        try:
            payload = encode_arelle_result(
                result,
                max_bytes=request.limits.max_serialized_bytes,
            )
        except Exception as exc:
            payload = encode_arelle_result(
                failed_arelle_result(
                    request.accession_number,
                    code="worker_result_oversized",
                    message=str(exc),
                ),
                max_bytes=request.limits.max_serialized_bytes,
            )
        connection.send_bytes(payload)
    finally:
        connection.close()


def _terminate_process(process: multiprocessing.Process) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=2.0)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=2.0)
