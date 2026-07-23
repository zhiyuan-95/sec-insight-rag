"""Isolated Arelle process boundary for one filing accession."""

from __future__ import annotations

import multiprocessing
import os
import time
from importlib.metadata import version
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from src.processing.arelle_evidence import (
    ARELLE_ADAPTER_VERSION,
    ARELLE_RESULT_COMPLETE,
    ARELLE_RESULT_SCHEMA_VERSION,
    ArelleDiagnosticRecord,
    ArelleFilingIdentity,
    ArelleFilingRequest,
    ArelleFilingResult,
    ArelleTimingRecord,
    failed_arelle_result,
    finalize_arelle_result,
)
from src.processing.arelle_extraction import extract_arelle_evidence, file_sha256


def process_arelle_accession(
    request: ArelleFilingRequest,
    *,
    timeout_seconds: float | None = None,
) -> ArelleFilingResult:
    """Process one accession in a fresh child and return its decoded result."""
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive when provided")

    started_at = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_arelle_worker_entry,
        args=(request, send_connection),
        name=f"arelle-{request.accession_number}",
    )
    process.start()
    send_connection.close()
    try:
        if timeout_seconds is not None and not receive_connection.poll(timeout_seconds):
            _stop_process(process)
            return _parent_failure_result(
                request,
                process.pid,
                "arelle_worker_timeout",
                f"Arelle worker exceeded {timeout_seconds:g} seconds",
                started_at,
            )
        try:
            payload = receive_connection.recv_bytes().decode("utf-8")
        except (EOFError, OSError, UnicodeDecodeError) as exc:
            process.join()
            return _parent_failure_result(
                request,
                process.pid,
                "arelle_worker_crash",
                f"Arelle worker did not return a result: {exc}",
                started_at,
            )
        process.join()
        if process.exitcode != 0:
            return _parent_failure_result(
                request,
                process.pid,
                "arelle_worker_crash",
                f"Arelle worker exited with code {process.exitcode}",
                started_at,
            )
        try:
            return ArelleFilingResult.from_json(payload)
        except (TypeError, ValueError) as exc:
            return _parent_failure_result(
                request,
                process.pid,
                "arelle_worker_malformed_result",
                str(exc),
                started_at,
            )
    finally:
        receive_connection.close()
        if process.is_alive():
            _stop_process(process)


def _arelle_worker_entry(request: ArelleFilingRequest, connection: Connection) -> None:
    started_at = time.perf_counter()
    session_closed = False
    try:
        result, session_closed = _run_arelle_session(request, started_at)
    except BaseException as exc:
        result = failed_arelle_result(
            request,
            arelle_version=_arelle_version(),
            diagnostic=ArelleDiagnosticRecord(
                severity="error",
                code="arelle_worker_failure",
                message=str(exc) or exc.__class__.__name__,
            ),
            worker_pid=os.getpid(),
            session_closed=session_closed,
            total_seconds=time.perf_counter() - started_at,
        )
    try:
        connection.send_bytes(result.to_json().encode("utf-8"))
    finally:
        connection.close()


def _run_arelle_session(
    request: ArelleFilingRequest,
    started_at: float,
) -> tuple[ArelleFilingResult, bool]:
    from arelle.api.Session import Session
    from arelle.RuntimeOptions import RuntimeOptions

    session = Session()
    try:
        with session:
            entry_point = Path(request.entry_point_path)
            if not entry_point.is_file():
                raise FileNotFoundError(
                    f"Arelle entry point does not exist: {request.entry_point_path}"
                )
            content_sha256 = file_sha256(entry_point)
            if (
                request.content_sha256 is not None
                and request.content_sha256 != content_sha256
            ):
                raise ValueError("Arelle entry point content hash did not match the request")
            load_started_at = time.perf_counter()
            options = RuntimeOptions(
                entrypointFile=str(entry_point),
                keepOpen=True,
                validate=True,
                validateEFM=True,
                formulaAction="run",
                formulaAsserResultCounts=True,
                logFile="logToStructuredMessage",
                logPropagate=False,
                disablePersistentConfig=True,
                internetConnectivity="offline",
                httpUserAgent=request.sec_user_agent,
            )
            run_succeeded = session.run(options)
            models = session.get_models()
            load_validate_seconds = time.perf_counter() - load_started_at
            if not run_succeeded or not models:
                raise RuntimeError("Arelle did not return a loaded model")
            model_xbrl = models[0]
            log_messages = session.get_log_messages()
            fatal_codes = _fatal_diagnostic_codes(log_messages)
            if fatal_codes:
                raise RuntimeError(
                    "Arelle reported fatal diagnostics: " + ", ".join(fatal_codes)
                )
            extraction_started_at = time.perf_counter()
            evidence = extract_arelle_evidence(
                model_xbrl,
                log_messages,
            )
            extraction_seconds = time.perf_counter() - extraction_started_at
            if not evidence.facts:
                raise RuntimeError("Arelle did not return a trustworthy core fact set")
        result = finalize_arelle_result(
            ArelleFilingResult(
                schema_version=ARELLE_RESULT_SCHEMA_VERSION,
                adapter_version=ARELLE_ADAPTER_VERSION,
                arelle_version=_arelle_version(),
                filing=ArelleFilingIdentity(
                    cik=request.cik,
                    accession_number=request.accession_number,
                    form=request.form,
                    filing_date=request.filing_date,
                    entry_point_path=request.entry_point_path,
                    source_url=request.source_url,
                ),
                status=ARELLE_RESULT_COMPLETE,
                facts=evidence.facts,
                concepts=evidence.concepts,
                contexts=evidence.contexts,
                units=evidence.units,
                relationships=evidence.relationships,
                formula_assertions=evidence.formula_assertions,
                diagnostics=evidence.diagnostics,
                namespaces=evidence.namespaces,
                source_documents=evidence.source_documents,
                record_counts=evidence.record_counts,
                timings=ArelleTimingRecord(
                    load_validate_seconds=load_validate_seconds,
                    extraction_seconds=extraction_seconds,
                    total_seconds=time.perf_counter() - started_at,
                ),
                content_sha256=content_sha256,
                payload_sha256="",
                worker_pid=os.getpid(),
                session_closed=True,
            )
        )
        return result, True
    except BaseException as exc:
        return (
            failed_arelle_result(
                request,
                arelle_version=_arelle_version(),
                diagnostic=ArelleDiagnosticRecord(
                    severity="error",
                    code="arelle_worker_failure",
                    message=str(exc) or exc.__class__.__name__,
                ),
                worker_pid=os.getpid(),
                session_closed=True,
                total_seconds=time.perf_counter() - started_at,
            ),
            True,
        )


def _parent_failure_result(
    request: ArelleFilingRequest,
    worker_pid: int | None,
    code: str,
    message: str,
    started_at: float,
) -> ArelleFilingResult:
    return failed_arelle_result(
        request,
        arelle_version=_arelle_version(),
        diagnostic=ArelleDiagnosticRecord(
            severity="error",
            code=code,
            message=message,
        ),
        worker_pid=worker_pid,
        session_closed=False,
        total_seconds=time.perf_counter() - started_at,
    )


def _stop_process(process: multiprocessing.Process) -> None:
    process.terminate()
    process.join()


def _arelle_version() -> str:
    return version("arelle-release")


def _fatal_diagnostic_codes(log_messages: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(message.get("messageCode") or "arelle:unknown")
                for message in log_messages
                if str(message.get("levelname") or "").upper()
                in {"CRITICAL", "FATAL"}
            }
        )
    )
