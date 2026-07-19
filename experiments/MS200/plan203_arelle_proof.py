"""Run the schema-free Plan 203 Arelle proof against live SEC filings."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_settings  # noqa: E402
from src.ingestion.arelle_adapter import verify_filing_entry_offline  # noqa: E402
from src.ingestion.arelle_worker import process_arelle_filing  # noqa: E402
from src.ingestion.companyfacts import get_companyfacts  # noqa: E402
from src.ingestion.errors import SecConfigurationError  # noqa: E402
from src.ingestion.filing_packages import (  # noqa: E402
    build_filing_package,
    filing_package_sha256,
    load_filing_package_manifest,
)
from src.ingestion.filings import FilingMetadata, select_latest_filings  # noqa: E402
from src.ingestion.sec_client import SecClient  # noqa: E402
from src.ingestion.submissions import get_company_submissions  # noqa: E402
from src.ingestion.taxonomy_packages import (  # noqa: E402
    DEFAULT_INSTALL_DIRECTORY,
    DEFAULT_REGISTRY_PATH,
    installed_taxonomy_package_paths,
    sync_taxonomy_packages,
    taxonomy_registry_sha256,
)
from src.ingestion.tickers import load_ticker_mapping, resolve_ticker_to_cik  # noqa: E402
from src.processing.arelle_codec import encode_arelle_result  # noqa: E402
from src.processing.arelle_precedence import apply_arelle_accession_precedence  # noqa: E402
from src.processing.arelle_reconciliation import (  # noqa: E402
    ArelleReconciliationSummary,
    reconcile_arelle_with_companyfacts,
)
from src.processing.arelle_records import (  # noqa: E402
    ArelleFilingRequest,
    ArelleFilingResult,
)
from src.processing.xbrl_normalizer import normalize_companyfacts  # noqa: E402


DEFAULT_REPORT_PATH = Path("experiments/MS200/experiment_report_plan203_arelle.md")


@dataclass(frozen=True)
class FilingProof:
    """Evidence retained for rendering one filing section."""

    requested_form: str
    filing: FilingMetadata | None = None
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    result: ArelleFilingResult | None = None
    payload_bytes: int = 0
    reconciliation: ArelleReconciliationSummary | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class Plan203ProofSession:
    """Structured, immutable evidence returned by one proof workflow run."""

    ticker: str
    cik: str
    requested_forms: tuple[str, ...]
    registry_path: Path
    registry_hash: str
    taxonomy_paths: tuple[Path, ...]
    companyfacts_count: int
    proofs: tuple[FilingProof, ...]
    elapsed_seconds: float
    stage_timings: tuple[tuple[str, float], ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build verified accession packages, run isolated Arelle workers, "
            "and reconcile their facts with SEC Company Facts."
        )
    )
    parser.add_argument("--ticker", default="MSFT")
    parser.add_argument("--env-file", default="config.env")
    parser.add_argument(
        "--forms",
        nargs="+",
        default=["10-K", "10-Q"],
        choices=["10-K", "10-Q"],
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--taxonomy-dir",
        type=Path,
        default=DEFAULT_INSTALL_DIRECTORY,
    )
    parser.add_argument(
        "--filings-dir",
        type=Path,
        help="Override STOCK_FILINGS_BASE_DIR for this proof.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data_store/arelle_cache/plan203"),
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--sync-taxonomies",
        action="store_true",
        help="Install missing exact packages before the run; otherwise only verify installed packages.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = run_plan203_proof(
        ticker=args.ticker,
        env_file=args.env_file,
        forms=tuple(args.forms),
        registry=args.registry,
        taxonomy_dir=args.taxonomy_dir,
        filings_dir=args.filings_dir,
        cache_dir=args.cache_dir,
        sync_taxonomies=args.sync_taxonomies,
    )
    report_path = _rooted(args.report)
    _write_report(
        report_path,
        ticker=session.ticker,
        cik=session.cik,
        registry_path=session.registry_path,
        registry_hash=session.registry_hash,
        taxonomy_paths=session.taxonomy_paths,
        companyfacts_count=session.companyfacts_count,
        proofs=list(session.proofs),
    )
    print(f"Plan 203 report: {report_path}")
    return 1 if any(
        proof.failure_reason
        or (proof.result is not None and proof.result.status == "failed")
        for proof in session.proofs
    ) else 0


def run_plan203_proof(
    *,
    ticker: str = "MSFT",
    env_file: str | Path = "config.env",
    forms: tuple[str, ...] = ("10-K", "10-Q"),
    registry: Path = DEFAULT_REGISTRY_PATH,
    taxonomy_dir: Path = DEFAULT_INSTALL_DIRECTORY,
    filings_dir: Path | None = None,
    cache_dir: Path = Path("data_store/arelle_cache/plan203"),
    sync_taxonomies: bool = False,
) -> Plan203ProofSession:
    """Run the proof once and return its evidence without rendering a report.

    SEC identity, submissions, Company Facts, and taxonomy registry failures are
    global prerequisites and still raise. Once filings are selected, a package
    or worker failure is isolated to its requested form so the other form can
    remain inspectable.
    """
    started = time.perf_counter()
    stage_timings: list[tuple[str, float]] = []
    settings = load_settings(env_file)
    if settings.sec_user_agent is None or not settings.sec_user_agent.strip():
        raise SecConfigurationError(
            "SEC_USER_AGENT is required for the live Plan 203 proof"
        )

    ticker = ticker.strip().upper()
    requested_forms = tuple(dict.fromkeys(form.strip().upper() for form in forms))
    unsupported = sorted(set(requested_forms) - {"10-K", "10-Q"})
    if unsupported:
        raise ValueError(f"Unsupported filing forms: {', '.join(unsupported)}")

    stage_started = time.perf_counter()
    client = SecClient(settings.sec_user_agent)
    mapping = load_ticker_mapping(client)
    cik = resolve_ticker_to_cik(ticker, mapping)
    submissions = get_company_submissions(client, cik)
    filings = select_latest_filings(submissions, set(requested_forms))
    companyfacts_payload = get_companyfacts(client, cik)
    companyfacts = normalize_companyfacts(
        companyfacts_payload,
        concepts=None,
        forms=None,
        taxonomies=None,
    )
    stage_timings.append(("sec_acquisition", time.perf_counter() - stage_started))

    stage_started = time.perf_counter()
    registry_path = _rooted(registry)
    taxonomy_directory = _rooted(taxonomy_dir)
    if sync_taxonomies:
        sync_taxonomy_packages(registry_path, taxonomy_directory)
    taxonomy_paths = installed_taxonomy_package_paths(
        registry_path,
        taxonomy_directory,
    )
    registry_hash = taxonomy_registry_sha256(registry_path)
    filings_directory = _rooted(filings_dir or settings.stock_filings_base_dir)
    cache_directory = _rooted(cache_dir) / registry_hash[:12]
    stage_timings.append(("taxonomy_verification", time.perf_counter() - stage_started))

    proofs: list[FilingProof] = []
    filings_by_form = {filing.form: filing for filing in filings}
    for requested_form in sorted(requested_forms):
        filing = filings_by_form.get(requested_form)
        if filing is None:
            proofs.append(
                FilingProof(
                    requested_form=requested_form,
                    failure_stage="sec_acquisition",
                    failure_reason=f"No latest {requested_form} filing was available",
                )
            )
            continue
        print(f"Plan 203: building/verifying {filing.form} {filing.accession_number}")
        package_started = time.perf_counter()
        try:
            manifest_path = build_filing_package(
                client,
                filing,
                filings_directory,
                taxonomy_registry_hash=registry_hash,
                taxonomy_package_paths=taxonomy_paths,
                offline_verifier=verify_filing_entry_offline,
            )
            manifest = load_filing_package_manifest(manifest_path)
            manifest_hash = filing_package_sha256(manifest_path)
        except Exception as exc:  # form-scoped evidence boundary
            stage_timings.append(
                (f"{requested_form}_package", time.perf_counter() - package_started)
            )
            proofs.append(
                FilingProof(
                    requested_form=requested_form,
                    filing=filing,
                    failure_stage="filing_package",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        stage_timings.append(
            (f"{requested_form}_package", time.perf_counter() - package_started)
        )
        request = ArelleFilingRequest(
            entry_document=str((manifest_path.parent / manifest.entry_document).resolve()),
            package_manifest=str(manifest_path.resolve()),
            cik=cik,
            accession_number=filing.accession_number,
            form=filing.form,
            filing_date=filing.filing_date,
            fiscal_year=None,
            fiscal_period=None,
            sec_user_agent=settings.sec_user_agent,
            cache_directory=str(cache_directory.resolve()),
            taxonomy_package_paths=tuple(str(path) for path in taxonomy_paths),
        )
        worker_started = time.perf_counter()
        try:
            result = process_arelle_filing(request)
            payload_bytes = len(
                encode_arelle_result(
                    result,
                    max_bytes=request.limits.max_serialized_bytes,
                )
            )
            reconciliation = reconcile_arelle_with_companyfacts(result, companyfacts)
        except Exception as exc:  # form-scoped evidence boundary
            stage_timings.append(
                (f"{requested_form}_arelle", time.perf_counter() - worker_started)
            )
            proofs.append(
                FilingProof(
                    requested_form=requested_form,
                    filing=filing,
                    manifest_path=manifest_path,
                    manifest_sha256=manifest_hash,
                    failure_stage="arelle_processing",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        stage_timings.append(
            (f"{requested_form}_arelle", time.perf_counter() - worker_started)
        )
        proofs.append(
            FilingProof(
                requested_form=requested_form,
                filing=filing,
                manifest_path=manifest_path,
                manifest_sha256=manifest_hash,
                result=result,
                payload_bytes=payload_bytes,
                reconciliation=reconciliation,
            )
        )
        print(
            f"Plan 203: {filing.form} status={result.status} "
            f"facts={result.counts.facts:,} concepts={result.counts.concepts:,} "
            f"relationships={result.counts.relationships:,} "
            f"diagnostics={result.counts.diagnostics:,}"
        )

    return Plan203ProofSession(
        ticker=ticker,
        cik=cik,
        requested_forms=requested_forms,
        registry_path=registry_path,
        registry_hash=registry_hash,
        taxonomy_paths=taxonomy_paths,
        companyfacts_count=len(companyfacts),
        proofs=tuple(proofs),
        elapsed_seconds=time.perf_counter() - started,
        stage_timings=tuple(stage_timings),
    )


def _write_report(
    report_path: Path,
    *,
    ticker: str,
    cik: str,
    registry_path: Path,
    registry_hash: str,
    taxonomy_paths: tuple[Path, ...],
    companyfacts_count: int,
    proofs: list[FilingProof],
) -> None:
    lines = [
        "# Plan 203 Arelle Integration Proof",
        "",
        "This is evidence from a schema-free proof run. It does not activate inferred mappings,",
        "write financial metrics, call an LLM, or change the database schema.",
        "",
        "## Run Identity",
        "",
        f"- Ticker: `{ticker}`",
        f"- CIK: `{cik}`",
        f"- Taxonomy registry: `{registry_path}`",
        f"- Taxonomy registry SHA-256: `{registry_hash}`",
        f"- Verified taxonomy archives: {len(taxonomy_paths):,}",
        f"- Normalized Company Facts observations: {companyfacts_count:,}",
        "",
        "## Filing Summary",
        "",
        "| Form | Accession | Status | Facts | Concepts | Relationships | Diagnostics | Payload bytes | Total seconds |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for proof in proofs:
        result = proof.result
        if result is None or proof.filing is None:
            lines.append(
                "| "
                + " | ".join(
                    [
                        proof.requested_form,
                        proof.filing.accession_number if proof.filing else "unavailable",
                        "failed",
                        "0",
                        "0",
                        "0",
                        "0",
                        "0",
                        "0.000",
                    ]
                )
                + " |"
            )
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    proof.filing.form,
                    proof.filing.accession_number,
                    result.status,
                    f"{result.counts.facts:,}",
                    f"{result.counts.concepts:,}",
                    f"{result.counts.relationships:,}",
                    f"{result.counts.diagnostics:,}",
                    f"{proof.payload_bytes:,}",
                    f"{result.timings.total_seconds:.3f}",
                ]
            )
            + " |"
        )

    precedence = apply_arelle_accession_precedence(
        [proof.result for proof in proofs if proof.result is not None]
    )
    precedence_flags = Counter(
        flag
        for observation in precedence.quarantined
        for flag in observation.quality_flags
    )
    lines.extend(
        [
            "",
            "## In-memory precedence",
            "",
            f"- Selected eligible semantic observations: {len(precedence.selected):,}",
            f"- Quarantined observations: {len(precedence.quarantined):,}",
        ]
    )
    if precedence_flags:
        for flag, count in precedence_flags.most_common():
            lines.append(f"- `{flag}`: {count:,}")

    for proof in proofs:
        if proof.result is None or proof.filing is None:
            lines.extend(
                [
                    "",
                    f"## {proof.requested_form} `unavailable`",
                    "",
                    "- Canonical eligibility: `no`",
                    f"- Failure stage: `{_cell(proof.failure_stage or 'unknown')}`",
                    f"- Failure reason: {_cell(proof.failure_reason or 'unknown')}",
                ]
            )
            continue
        result = proof.result
        reconciliation = proof.reconciliation
        if proof.manifest_path is None or reconciliation is None:
            raise ValueError("Completed filing proof is missing report evidence")
        manifest = load_filing_package_manifest(proof.manifest_path)
        lines.extend(
            [
                "",
                f"## {proof.filing.form} `{proof.filing.accession_number}`",
                "",
                f"- Filing date: `{proof.filing.filing_date}`",
                f"- Manifest: `{proof.manifest_path}`",
                f"- Manifest SHA-256: `{proof.manifest_sha256}`",
                f"- Package verification: `{manifest.verification_status}`",
                f"- Empty-cache offline dependency proof: `{'yes' if manifest.verification_status == 'arelle_offline_verified' else 'no'}`",
                f"- Arelle version: `{result.arelle_version or 'unavailable'}`",
                "- Worker network mode: `offline`",
                f"- Worker cache state: `{result.cache_state}`",
                f"- Canonical eligibility: `{'yes' if result.status == 'complete' else 'no'}`",
                f"- Timing: load/validation `{result.timings.load_seconds:.3f}s`, "
                f"extraction `{result.timings.extraction_seconds:.3f}s`, "
                f"total `{result.timings.total_seconds:.3f}s`",
                "",
                "### Company Facts reconciliation",
                "",
                "The comparison key is accession + taxonomy family + local concept name + consolidated period + unit.",
                "Company Facts does not expose the versioned namespace URI; the full Arelle namespace remains lineage evidence and is not a system-metric mapping key.",
                "",
                f"- Arelle facts considered: {reconciliation.arelle_facts_considered:,}",
                f"- Company Facts observations considered: {reconciliation.companyfacts_facts_considered:,}",
                f"- Exact one-to-one value matches: {reconciliation.exact_matches:,}",
                f"- One-to-one value conflicts: {reconciliation.value_conflicts:,}",
                f"- Ambiguous duplicate keys: {reconciliation.ambiguous_keys:,}",
                f"- Arelle-only facts: {reconciliation.arelle_only_facts:,}",
                f"- Company-Facts-only observations: {reconciliation.companyfacts_only_facts:,}",
                "",
                "### Diagnostics",
                "",
            ]
        )
        diagnostic_counts = Counter(
            (item.severity, item.code) for item in result.diagnostics
        )
        if diagnostic_counts:
            lines.extend(
                [
                    "| Severity | Code | Count |",
                    "|---|---|---:|",
                    *[
                        f"| {severity} | `{_cell(code)}` | {count:,} |"
                        for (severity, code), count in diagnostic_counts.most_common(20)
                    ],
                ]
            )
            first_by_code = {}
            for diagnostic in result.diagnostics:
                first_by_code.setdefault(diagnostic.code, diagnostic.message)
            lines.extend(["", "Diagnostic examples:", ""])
            for code, message in list(first_by_code.items())[:10]:
                lines.append(f"- `{_cell(code)}`: {_cell(message)}")
        else:
            lines.append("No diagnostics were emitted.")

        if reconciliation.conflicts:
            lines.extend(
                [
                    "",
                    "### Value conflict sample",
                    "",
                    "| Taxonomy | Concept | Period | Unit | Arelle | Company Facts |",
                    "|---|---|---|---|---:|---:|",
                ]
            )
            for conflict in reconciliation.conflicts[:20]:
                period = (
                    f"{conflict.key.start_date or ''}..{conflict.key.end_date or ''}"
                )
                lines.append(
                    f"| `{_cell(conflict.key.taxonomy)}` | `{_cell(conflict.key.concept_local_name)}` | `{_cell(period)}` | "
                    f"`{_cell(conflict.key.unit)}` | `{_cell(conflict.arelle_value)}` | "
                    f"`{_cell(conflict.companyfacts_value)}` |"
                )

    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "Only a `complete` Arelle result is eligible to become canonical in a later increment.",
            "A `degraded` or `failed` result remains diagnostic evidence and cannot overwrite metrics.",
            "This proof reports reconciliation differences without selecting a winner.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_name(
        f".{report_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    temporary.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.replace(temporary, report_path)
    finally:
        temporary.unlink(missing_ok=True)


def _rooted(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
