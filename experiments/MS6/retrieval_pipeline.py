"""Run the MS6 local filing retrieval experiment."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import load_settings  # noqa: E402
from src.retrieval import (  # noqa: E402
    IndexSyncResult,
    RetrievedEvidence,
    RetrievalError,
    retrieve_filing_evidence,
    sync_company_retrieval_index,
)


@dataclass(frozen=True)
class QueryRun:
    """Retrieved evidence and timing for one experiment query."""

    query: str
    timing_label: str
    evidence: tuple[RetrievedEvidence, ...]
    elapsed_seconds: float


def main() -> int:
    """Build or reuse a local index and save a detailed text report."""
    args = _parse_args()
    ticker = args.ticker.strip().upper()
    report_path = (
        args.report_path.resolve()
        if args.report_path is not None
        else Path(__file__).resolve().parent / f"experiment_report_{ticker}.txt"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    captured_output = io.StringIO()
    embedding_model_cached_before_sync = _embedding_model_cached_before_sync(
        settings.knowledge_storage_dir,
    )

    try:
        with _captured_dependency_output(captured_output, verbose=args.verbose):
            sync_result = sync_company_retrieval_index(
                ticker,
                settings,
                force_rebuild=args.force_rebuild,
            )
            query_runs = tuple(
                _run_query(
                    ticker,
                    query,
                    settings,
                    timing_label=(
                        "initial cold-query duration"
                        if index == 0
                        else "subsequent warm-query duration"
                    ),
                )
                for index, query in enumerate(args.query)
            )
        report = _render_report(
            mode=args.mode,
            sync_result=sync_result,
            query_runs=query_runs,
            database_path=settings.stock_sql_db_path.resolve(),
            knowledge_storage=settings.knowledge_storage_dir.resolve(),
            embedding_model=settings.retrieval_embedding_model,
            chunk_size=settings.retrieval_chunk_size,
            chunk_overlap=settings.retrieval_chunk_overlap,
            embedding_model_cached_before_sync=embedding_model_cached_before_sync,
            captured_output=captured_output.getvalue(),
        )
        report_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        report_path.write_text(
            _render_error_report(
                ticker=ticker,
                mode=args.mode,
                error=exc,
                captured_output=captured_output.getvalue(),
                traceback_text=traceback.format_exc(),
            ),
            encoding="utf-8",
        )
        print(f"MS6 failed for {ticker}; details saved to {report_path}")
        return 1

    print(
        f"MS6 {sync_result.status} {sync_result.chunk_count} chunks for {ticker}; "
        f"report saved to {report_path}"
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect local SEC filing retrieval")
    parser.add_argument("--ticker", required=True, help="Locally ingested ticker")
    parser.add_argument(
        "--query",
        action="append",
        required=True,
        help="Retrieval query; repeat the option to run multiple queries",
    )
    parser.add_argument("--mode", choices=("local",), default="local")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--report-path", type=Path)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Allow dependency output in the terminal while the experiment runs",
    )
    return parser.parse_args()


def _captured_dependency_output(
    output: io.StringIO,
    *,
    verbose: bool,
) -> contextlib.AbstractContextManager[object]:
    if verbose:
        return contextlib.nullcontext()
    return _redirect_output(output)


@contextlib.contextmanager
def _redirect_output(output: io.StringIO):
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        yield


def _run_query(
    ticker: str,
    query: str,
    settings: object,
    *,
    timing_label: str,
) -> QueryRun:
    started = time.perf_counter()
    evidence = retrieve_filing_evidence(ticker, query, settings)
    return QueryRun(
        query=query,
        timing_label=timing_label,
        evidence=evidence,
        elapsed_seconds=time.perf_counter() - started,
    )


def _embedding_model_cached_before_sync(knowledge_storage: Path) -> bool:
    cache_dir = knowledge_storage / "model_cache" / "fastembed"
    try:
        return cache_dir.exists() and any(cache_dir.iterdir())
    except OSError:
        return False


def _render_report(
    *,
    mode: str,
    sync_result: IndexSyncResult,
    query_runs: tuple[QueryRun, ...],
    database_path: Path,
    knowledge_storage: Path,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model_cached_before_sync: bool,
    captured_output: str,
) -> str:
    lines = [
        "MS6 Experiment: Retrieval Pipeline",
        "=" * 42,
        "",
        "Run Context:",
        f"  generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"  mode: {mode}",
        f"  ticker: {sync_result.ticker}",
        f"  cik: {sync_result.cik}",
        f"  database: {database_path}",
        f"  knowledge_storage: {knowledge_storage}",
        f"  embedding_model: {embedding_model}",
        f"  embedding_model_cached_before_sync: {'yes' if embedding_model_cached_before_sync else 'no'}",
        f"  chunk_size: {chunk_size}",
        f"  chunk_overlap: {chunk_overlap}",
        "",
        "Index Summary:",
        f"  status: {sync_result.status}",
        f"  generation_id: {sync_result.generation_id}",
        f"  artifact_path: {sync_result.artifact_path}",
        f"  active_filing_count: {sync_result.filing_count}",
        f"  chunk_count: {sync_result.chunk_count}",
        f"  retrieval_synchronization_duration_seconds: {sync_result.elapsed_seconds:.3f}",
        "",
        "Filing And Section Coverage:",
    ]
    filing_rows = [
        (
            summary.form_type,
            summary.filing_date.isoformat(),
            summary.accession_number,
            str(summary.chunk_count),
            "yes" if summary.used_fallback else "no",
            ", ".join(summary.section_names),
        )
        for summary in sync_result.filing_summaries
    ]
    lines.extend(
        _format_table(
            ("form", "filing_date", "accession", "chunks", "fallback", "sections"),
            filing_rows,
        )
    )
    lines.extend(["", "Warnings:"])
    if sync_result.warnings:
        lines.extend(f"  - {warning}" for warning in sync_result.warnings)
    else:
        lines.append("  none")

    for query_run in query_runs:
        lines.extend(
            [
                "",
                f"Query: {query_run.query}",
                f"Timing Label: {query_run.timing_label}",
                f"{query_run.timing_label}: {query_run.elapsed_seconds:.3f} seconds",
                "",
                "Top Retrieved Evidence:",
            ]
        )
        evidence_rows = [
            (
                str(item.rank),
                f"{item.fused_score:.6f}",
                _optional_score(item.vector_score),
                _optional_score(item.bm25_score),
                item.form_type,
                item.filing_date.isoformat(),
                item.section_name,
                item.accession_number,
            )
            for item in query_run.evidence
        ]
        lines.extend(
            _format_table(
                (
                    "rank",
                    "fused",
                    "vector",
                    "bm25",
                    "form",
                    "filing_date",
                    "section",
                    "accession",
                ),
                evidence_rows,
            )
            if evidence_rows
            else ["  no evidence retrieved"]
        )
        lines.extend(["", "Full Evidence:"])
        if not query_run.evidence:
            lines.append("  none")
        for item in query_run.evidence:
            preview = " ".join(item.text.split())[:900]
            lines.extend(
                [
                    f"  Rank {item.rank}",
                    f"    chunk_id: {item.chunk_id}",
                    f"    text_sha256: {item.text_sha256}",
                    f"    section: {item.section_name} ({item.section_title})",
                    f"    form_and_date: {item.form_type} {item.filing_date.isoformat()}",
                    f"    accession: {item.accession_number}",
                    f"    vector_rank_score: {item.vector_rank} / {_optional_score(item.vector_score)}",
                    f"    bm25_rank_score: {item.bm25_rank} / {_optional_score(item.bm25_score)}",
                    f"    fused_score: {item.fused_score:.6f}",
                    f"    source_path: {item.source_path}",
                    f"    source_url: {item.source_url or 'not available'}",
                    f"    preview: {preview}",
                    "",
                ]
            )

    lines.extend(
        [
            "Artifact Integrity:",
            "  Canonical chunks and lineage are stored in SQLite.",
            "  Vector and BM25 artifacts are rebuildable from those chunks.",
            "  Retrieval validates generation and chunk-set hashes before use.",
        ]
    )
    if captured_output.strip():
        lines.extend(
            [
                "",
                "Captured Dependency Output:",
                captured_output.strip(),
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_error_report(
    *,
    ticker: str,
    mode: str,
    error: Exception,
    captured_output: str,
    traceback_text: str,
) -> str:
    lines = [
        "MS6 Experiment: Retrieval Pipeline",
        "=" * 42,
        "",
        "Run Context:",
        f"  generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"  mode: {mode}",
        f"  ticker: {ticker}",
        "",
        "Experiment Error:",
        f"  type: {type(error).__name__}",
        f"  message: {error}",
        "  recovery: correct the reported local data or configuration problem and rerun the command",
    ]
    if not isinstance(error, (RetrievalError, OSError, ValueError)):
        lines.extend(["", "Unexpected Error Traceback:", traceback_text.rstrip()])
    if captured_output.strip():
        lines.extend(["", "Captured Dependency Output:", captured_output.strip()])
    return "\n".join(lines).rstrip() + "\n"


def _format_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    header_line = "  " + " | ".join(
        header.ljust(widths[index]) for index, header in enumerate(headers)
    )
    divider = "  " + "-+-".join("-" * width for width in widths)
    body = [
        "  " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    ]
    return [header_line, divider, *body]


def _optional_score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
