"""Render an inspectable Milestone 203 view of the existing Plan 203 workflow."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.MS200.plan203_arelle_proof import (  # noqa: E402
    DEFAULT_INSTALL_DIRECTORY,
    DEFAULT_REGISTRY_PATH,
    FilingProof,
    Plan203ProofSession,
    run_plan203_proof,
)
from src.config import load_settings  # noqa: E402
from src.processing.active_window import active_period_keys  # noqa: E402
from src.processing.arelle_mapping_inference import (  # noqa: E402
    ArelleInferenceResult,
    infer_arelle_evidence_mappings,
)
from src.processing.arelle_precedence import (  # noqa: E402
    DUPLICATE_FACT,
    ArelleObservation,
    apply_arelle_accession_precedence,
)
from src.processing.arelle_records import ConceptEvidence, QNameKey, UnitKey  # noqa: E402
from src.processing.base_metrics import map_raw_facts_to_base_metrics  # noqa: E402
from src.processing.company_industry_labels import (  # noqa: E402
    LABEL_STATUS_ASSIGNED,
    industry_label_assignments_for_company,
)
from src.processing.mapping_catalog import (  # noqa: E402
    IndustryFactTarget,
    mapping_candidates_by_key,
)
from src.processing.mapping_targets import (  # noqa: E402
    CanonicalMetricTarget,
    canonical_metric_targets,
)
from src.processing.xbrl_normalizer import NormalizedFact  # noqa: E402
from src.storage.concept_mappings_repository import (  # noqa: E402
    MAPPING_SCOPE_COMPANY,
    MAPPING_SCOPE_GLOBAL,
    MAPPING_SCOPE_INDUSTRY,
    MAPPING_STATUS_APPROVED,
    ConceptMappingRecord,
    ConceptMappingRepository,
)
from src.storage.database import connect_sqlite_readonly  # noqa: E402


DEFAULT_CACHE_DIRECTORY = Path("data_store/arelle_cache/plan203")
EXIT_COMPLETE = 0
EXIT_FATAL = 1
EXIT_INCOMPLETE = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect SEC acquisition, Arelle evidence, fact selection, current "
            "hard mapping, and report-only deterministic inference."
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
    parser.add_argument("--taxonomy-dir", type=Path, default=DEFAULT_INSTALL_DIRECTORY)
    parser.add_argument("--filings-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIRECTORY)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sync-taxonomies", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ticker = args.ticker.strip().upper()
    report_path = _rooted(
        args.report
        or Path(f"experiments/MS200/milestone203_mapping_report_{ticker}.md")
    )
    try:
        settings = load_settings(args.env_file)
        session = run_plan203_proof(
            ticker=ticker,
            env_file=args.env_file,
            forms=tuple(args.forms),
            registry=args.registry,
            taxonomy_dir=args.taxonomy_dir,
            filings_dir=args.filings_dir,
            cache_dir=args.cache_dir,
            sync_taxonomies=args.sync_taxonomies,
        )
        report = build_milestone203_report(
            session,
            database_path=_rooted(args.database or settings.stock_sql_db_path),
        )
        _atomic_write(report_path, report)
    except Exception as exc:
        print(f"Milestone 203 failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FATAL

    print(
        f"Milestone 203 inspection complete in {session.elapsed_seconds:.3f}s; "
        f"saved report: {report_path}"
    )
    eligible = [
        proof
        for proof in session.proofs
        if proof.result is not None and proof.result.status == "complete"
    ]
    if not eligible:
        return EXIT_FATAL
    if len(eligible) != len(session.requested_forms):
        return EXIT_INCOMPLETE
    return EXIT_COMPLETE


def build_milestone203_report(
    session: Plan203ProofSession,
    *,
    database_path: Path,
) -> str:
    """Project the proof session into a read-only, human-inspectable report."""
    report_started = time.perf_counter()
    completed_results = tuple(
        proof.result for proof in session.proofs if proof.result is not None
    )
    precedence = apply_arelle_accession_precedence(completed_results)
    evidence_by_qname = {
        concept.concept_key: concept
        for result in completed_results
        for concept in result.concepts
    }
    normalized_rows = tuple(
        _normalize_observation(observation, session.cik, evidence_by_qname)
        for observation in precedence.selected
    )
    industry_assignment = industry_label_assignments_for_company(
        session.ticker,
        session.cik,
        observed_concepts=(fact.concept for fact in normalized_rows),
    )
    industry_labels = (
        industry_assignment.assigned_industry_labels
        if industry_assignment.label_status == LABEL_STATUS_ASSIGNED
        else ()
    )
    targets = canonical_metric_targets(industry_labels)
    approved_rows, mapping_conflicts, mapping_store_status = _load_approved_mapping_rows(
        database_path,
        cik=session.cik,
        industry_labels=industry_labels,
    )
    approved_mappings, approved_sources = _collapse_approved_mappings(
        approved_rows,
        cik=session.cik,
        industry_labels=industry_labels,
    )
    blocked_selectors = frozenset(mapping_conflicts)
    usable_rows = tuple(
        (index, fact)
        for index, fact in enumerate(normalized_rows, start=1)
        if (fact.taxonomy, fact.concept) not in blocked_selectors
    )
    active_keys = active_period_keys(fact for _, fact in usable_rows)
    mapped_metrics = map_raw_facts_to_base_metrics(
        usable_rows,
        active_keys,
        industry_labels=industry_labels,
        additional_mappings=approved_mappings,
    )
    mapped_target_keys = {
        (metric.metric_name, metric.statement_type) for metric in mapped_metrics
    }
    mapped_targets = tuple(
        target
        for target in targets
        if (target.metric_name, target.statement_type) in mapped_target_keys
    )
    missing_targets = tuple(target for target in targets if target not in mapped_targets)
    reconciliation_conflicts = _reconciliation_conflict_keys(session.proofs)
    inference = infer_arelle_evidence_mappings(
        completed_results,
        missing_targets=missing_targets,
        applicable_targets=targets,
        reconciliation_conflicts=reconciliation_conflicts,
    )
    metric_sources = _metric_sources(
        normalized_rows,
        industry_labels=industry_labels,
        approved_mappings=approved_mappings,
        approved_sources=approved_sources,
        blocked_selectors=blocked_selectors,
    )
    return _render_report(
        session,
        database_path=database_path,
        precedence=precedence,
        normalized_rows=normalized_rows,
        industry_assignment=industry_assignment,
        targets=targets,
        mapped_targets=mapped_targets,
        missing_targets=missing_targets,
        inference=inference,
        mapped_metrics=mapped_metrics,
        metric_sources=metric_sources,
        mapping_conflicts=mapping_conflicts,
        mapping_store_status=mapping_store_status,
        report_elapsed=time.perf_counter() - report_started,
    )


def _load_approved_mapping_rows(
    database_path: Path,
    *,
    cik: str,
    industry_labels: tuple[str, ...],
) -> tuple[
    tuple[ConceptMappingRecord, ...],
    tuple[tuple[str, str], ...],
    str,
]:
    with connect_sqlite_readonly(database_path) as connection:
        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'xbrl_concept_mappings'
            """
        ).fetchone()
        if table_exists is None:
            return (), (), "table_missing_read_only; source-controlled mappings only"
        repository = ConceptMappingRepository(connection)
        try:
            rows = repository.list_for_company(
                cik,
                industry_labels,
                status=MAPPING_STATUS_APPROVED,
            )
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                "Approved mapping table exists but cannot be inspected read-only"
            ) from exc
    conflicts = _mapping_conflict_selectors(
        rows,
        cik=cik,
        industry_labels=industry_labels,
    )
    return rows, conflicts, f"available; {len(rows)} applicable approved rows"


def _mapping_conflict_selectors(
    rows: Iterable[ConceptMappingRecord],
    *,
    cik: str,
    industry_labels: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    by_selector: dict[tuple[str, str], list[ConceptMappingRecord]] = defaultdict(list)
    for row in rows:
        by_selector[(row.taxonomy, row.concept)].append(row)
    conflicts: list[tuple[str, str]] = []
    for selector, candidates in by_selector.items():
        ranks = [_mapping_scope_rank(row, cik, industry_labels) for row in candidates]
        top_rank = max(ranks)
        winners = [row for row, rank in zip(candidates, ranks) if rank == top_rank]
        decisions = {(row.metric_name, row.statement_type) for row in winners}
        if len(decisions) > 1:
            conflicts.append(selector)
    return tuple(sorted(conflicts))


def _collapse_approved_mappings(
    rows: Iterable[ConceptMappingRecord],
    *,
    cik: str,
    industry_labels: tuple[str, ...],
) -> tuple[
    dict[tuple[str, str], IndustryFactTarget],
    dict[tuple[str, str], str],
]:
    conflicts = set(
        _mapping_conflict_selectors(rows, cik=cik, industry_labels=industry_labels)
    )
    by_selector: dict[tuple[str, str], list[ConceptMappingRecord]] = defaultdict(list)
    for row in rows:
        by_selector[(row.taxonomy, row.concept)].append(row)
    mappings: dict[tuple[str, str], IndustryFactTarget] = {}
    sources: dict[tuple[str, str], str] = {}
    for selector, candidates in sorted(by_selector.items()):
        if selector in conflicts:
            continue
        winner = min(
            candidates,
            key=lambda row: (
                -_mapping_scope_rank(row, cik, industry_labels),
                -(row.confidence or 0.0),
                row.metric_name,
                row.statement_type,
                row.mapping_id or 0,
            ),
        )
        mappings[selector] = IndustryFactTarget(
            industry_label=winner.scope_value or "approved_global",
            raw_concept=winner.concept,
            taxonomy=winner.taxonomy,
            internal_metric_name=winner.metric_name,
            statement_type=winner.statement_type,
            required_for_core=False,
            required_for_specialized_indicators=False,
            consolidated_or_segment="consolidated",
            priority=0,
            notes=f"Approved {winner.scope_type} mapping #{winner.mapping_id or 'unpersisted'}",
        )
        sources[selector] = (
            f"approved {winner.scope_type} mapping #{winner.mapping_id or 'unpersisted'}"
        )
    return mappings, sources


def _mapping_scope_rank(
    row: ConceptMappingRecord,
    cik: str,
    industry_labels: tuple[str, ...],
) -> int:
    if row.scope_type == MAPPING_SCOPE_COMPANY and row.scope_value == cik:
        return 3
    if row.scope_type == MAPPING_SCOPE_INDUSTRY and row.scope_value in industry_labels:
        return 2
    if row.scope_type == MAPPING_SCOPE_GLOBAL:
        return 1
    return 0


def _normalize_observation(
    observation: ArelleObservation,
    cik: str,
    evidence_by_qname: Mapping[QNameKey, ConceptEvidence],
) -> NormalizedFact:
    fact = observation.fact
    context = fact.context_key
    evidence = evidence_by_qname.get(fact.concept_key)
    start_date = _date_or_none(context.start_date)
    end_date = _date_or_none(context.instant_date or context.end_date)
    filing_date = _date_or_none(observation.filing_date)
    fiscal_year = end_date.year if end_date else None
    fiscal_period = "FY" if (observation.form or "").upper().startswith("10-K") else None
    value = _decimal_or_none(fact.value) if evidence is None or evidence.is_numeric else None
    return NormalizedFact(
        cik=cik,
        entity_name=None,
        taxonomy=_taxonomy_name(fact.concept_key),
        concept=fact.concept_key.local_name,
        label=evidence.standard_label if evidence else None,
        description=evidence.documentation if evidence else None,
        unit=_unit_text(fact.unit_key),
        value_raw=fact.value_raw,
        value=value,
        start_date=start_date,
        end_date=end_date,
        period_type=context.period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=observation.form,
        filed_date=filing_date,
        accession_number=observation.accession_number,
        frame=None,
        source="sec_arelle_plan203",
        quality_flags=observation.quality_flags,
        namespace_uri=fact.concept_key.namespace_uri,
        context_id=context.context_id,
        dimensions=tuple(
            (
                _qname_text(dimension.dimension),
                _qname_text(dimension.member)
                if dimension.member is not None
                else dimension.typed_member_xml or "",
            )
            for dimension in context.dimensions
        ),
        is_consolidated=not context.dimensions,
        source_document=fact.source_document,
        balance=evidence.balance if evidence else None,
        is_numeric=evidence.is_numeric if evidence else value is not None,
    )


def _metric_sources(
    facts: Iterable[NormalizedFact],
    *,
    industry_labels: tuple[str, ...],
    approved_mappings: Mapping[tuple[str, str], IndustryFactTarget],
    approved_sources: Mapping[tuple[str, str], str],
    blocked_selectors: frozenset[tuple[str, str]],
) -> dict[tuple[str, str], tuple[str, ...]]:
    catalog = mapping_candidates_by_key(industry_labels)
    sources: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fact in facts:
        selector = (fact.taxonomy, fact.concept)
        if selector in blocked_selectors or not fact.is_consolidated or fact.value is None:
            continue
        target = approved_mappings.get(selector) or catalog.get(selector)
        if target is None:
            continue
        source = approved_sources.get(selector, "source-controlled hard mapping")
        text = f"{fact.taxonomy}:{fact.concept} via {source}"
        key = (target.metric_name, target.statement_type)
        if text not in sources[key]:
            sources[key].append(text)
    return {key: tuple(values) for key, values in sources.items()}


def _reconciliation_conflict_keys(
    proofs: Iterable[FilingProof],
) -> dict[str, frozenset[tuple[str, str]]]:
    output: dict[str, frozenset[tuple[str, str]]] = {}
    for proof in proofs:
        if proof.filing is None or proof.reconciliation is None:
            continue
        output[proof.filing.accession_number] = frozenset(
            (conflict.key.taxonomy, conflict.key.concept_local_name)
            for conflict in proof.reconciliation.conflicts
        )
    return output


def _render_report(
    session: Plan203ProofSession,
    *,
    database_path: Path,
    precedence: object,
    normalized_rows: tuple[NormalizedFact, ...],
    industry_assignment: object,
    targets: tuple[CanonicalMetricTarget, ...],
    mapped_targets: tuple[CanonicalMetricTarget, ...],
    missing_targets: tuple[CanonicalMetricTarget, ...],
    inference: tuple[ArelleInferenceResult, ...],
    mapped_metrics: list[object],
    metric_sources: Mapping[tuple[str, str], tuple[str, ...]],
    mapping_conflicts: tuple[tuple[str, str], ...],
    mapping_store_status: str,
    report_elapsed: float,
) -> str:
    selected = precedence.selected
    quarantined = precedence.quarantined
    raw_fact_count = sum(
        proof.result.counts.facts for proof in session.proofs if proof.result is not None
    )
    qname_count = len(
        {
            fact.concept_key
            for proof in session.proofs
            if proof.result is not None
            for fact in proof.result.facts
        }
    )
    selected_occurrences = sum(item.occurrence_count for item in selected)
    quarantined_occurrences = sum(item.occurrence_count for item in quarantined)
    count_integrity = raw_fact_count == selected_occurrences + quarantined_occurrences
    duplicate_groups = sum(DUPLICATE_FACT in item.quality_flags for item in quarantined)
    duplicate_occurrences = sum(
        item.occurrence_count
        for item in quarantined
        if DUPLICATE_FACT in item.quality_flags
    )
    complete_forms = sum(
        proof.result is not None and proof.result.status == "complete"
        for proof in session.proofs
    )
    completion_index = (
        100.0 * complete_forms / len(session.requested_forms)
        if session.requested_forms
        else 0.0
    )
    lines = [
        "# Milestone 203 Arelle Mapping Inspection",
        "",
        "This report presents the existing workflow. It does not change schemas, write data,",
        "activate inferred mappings, generate formulas, or call an LLM.",
        "",
        "## 0. Workflow Walkthrough",
        "",
        "| Stage | Input | Action | Output | Stop boundary | Count / time | Inspect |",
        "|---|---|---|---|---|---|---|",
        f"| SEC acquisition | `{session.ticker}` + requested forms | Fetch identity, submissions, filings, Company Facts | {len(session.proofs)} form records | Network acquisition only | {_stage_time(session, 'sec_acquisition'):.3f}s | [Summary](#a-summary) |",
        f"| Arelle processing | Verified accession packages | Offline load, validation, extraction | {raw_fact_count:,} facts / {qname_count:,} QNames | Detached project records | {session.elapsed_seconds:.3f}s proof session | [Per-accession evidence](#a1-per-accession-evidence) |",
        f"| Fact selection | Arelle facts | Duplicate, nil, degraded, and precedence handling | {len(selected):,} selected / {len(quarantined):,} quarantined semantic observations | In memory only | {selected_occurrences + quarantined_occurrences:,} raw occurrences | [Selection accounting](#a2-selection-accounting) |",
        f"| Target selection | Source-controlled company labels | Common bundle + applicable industry bundle | {len(targets):,} target metrics | No new target identity | `{_cell(industry_assignment.label_status)}` | [Mapping status](#b-target-metrics-mapping-status) |",
        f"| Hard mapping | Selected facts + catalog + approved SQLite rows | Existing deterministic mapper | {len(mapped_targets):,} mapped / {len(missing_targets):,} missing targets | No metric persistence | {len(mapped_metrics):,} mapped fact observations | [Mapped targets](#b1-mapped-targets) |",
        f"| Evidence inference | Missing targets + Arelle taxonomy evidence | Deterministic shadow ranking | {sum(row.outcome == 'unique_top_candidate' for row in inference):,} unique / {sum(row.outcome == 'needs_review' for row in inference):,} review / {sum(row.outcome == 'no_candidate' for row in inference):,} none | Never activated | 0 LLM calls | [Inference](#c-arelle-evidence-inference) |",
        f"| Report publication | Structured session evidence | Render and atomic replace | This Markdown artifact | Presentation only | {report_elapsed:.3f}s before publication | [Boundary](#d-interpretation-boundary) |",
        "",
        "## A. Summary",
        "",
        f"- Ticker / CIK: `{session.ticker}` / `{session.cik}`",
        f"- Requested forms: `{', '.join(session.requested_forms)}`",
        f"- Completion index: `{completion_index:.1f}` (complete requested forms / requested forms x 100; higher means more complete)",
        f"- Arelle result complete for every requested form: `{'Y' if complete_forms == len(session.requested_forms) else 'N'}`",
        f"- Raw facts processed: {raw_fact_count:,}",
        f"- Raw QName concepts involved: {qname_count:,}",
        f"- Selected eligible semantic observations: {len(selected):,}",
        f"- Quarantined semantic observations: {len(quarantined):,}",
        f"- Duplicate groups / raw occurrences: {duplicate_groups:,} / {duplicate_occurrences:,}",
        f"- Fact eligible for mapping: `{'Y' if selected else 'N'}`",
        f"- Count integrity: `{'Y' if count_integrity else 'N'}` ({raw_fact_count:,} raw = {selected_occurrences:,} selected occurrences + {quarantined_occurrences:,} quarantined occurrences)",
        f"- Industry bundle: `{', '.join(industry_assignment.assigned_industry_labels) or 'common-only'}`",
        f"- Industry-label status: `{industry_assignment.label_status}`",
        f"- Read-only mapping database: `{database_path}`",
        f"- Approved mapping store status: `{mapping_store_status}`",
        f"- Approved-mapping selector conflicts excluded: {len(mapping_conflicts):,}",
        f"- Proof workflow elapsed: {session.elapsed_seconds:.3f}s",
        f"- Report projection elapsed before atomic publication: {report_elapsed:.3f}s",
        "- Shadow inference policy: `arelle-evidence-inference-v1`; threshold `uncalibrated_shadow`; evidence independence `not_assumed`.",
        "- External model/provider calls during mapping and inference: `0`.",
        "",
        "### A1. Per-accession evidence",
        "",
        "| Form | Accession | Arelle complete? | Reason when no | Raw facts | QName concepts | Selected | Quarantined | Duplicate groups | Fact eligible? | Arelle seconds |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for proof in sorted(session.proofs, key=_proof_order):
        lines.append(_proof_summary_row(proof))
    lines.extend(
        [
            "",
            "### A2. Selection accounting",
            "",
            "Quarantine reasons may overlap; a duplicate in a degraded accession is counted under both reason labels.",
            "Raw-occurrence integrity uses each semantic observation's occurrence count, not the number of grouped rows.",
            "",
        ]
    )
    flags = Counter(flag for item in quarantined for flag in item.quality_flags)
    if flags:
        lines.extend([f"- `{flag}`: {count:,} semantic observations" for flag, count in flags.most_common()])
    else:
        lines.append("- No observations were quarantined.")
    if mapping_conflicts:
        lines.extend(["", "Approved mapping conflicts (excluded):", ""])
        lines.extend(f"- `{taxonomy}:{concept}`" for taxonomy, concept in mapping_conflicts)

    lines.extend(
        [
            "",
            "## B. Target Metrics Mapping Status",
            "",
            f"All {len(targets):,} applicable canonical targets are shown exactly once below.",
            "The target objects come from the existing catalog; statement type is metadata, not a new metric identity.",
            "",
            "### B1. Mapped targets",
            "",
            "| Metric | Statement | Source concept and mapping authority | Mapped observations |",
            "|---|---|---|---:|",
        ]
    )
    metric_counts = Counter(
        (metric.metric_name, metric.statement_type) for metric in mapped_metrics
    )
    for target in mapped_targets:
        key = (target.metric_name, target.statement_type)
        lines.append(
            f"| `{target.metric_name}` | `{target.statement_type}` | {_cell('; '.join(metric_sources.get(key, ('mapped by existing hard mapper',))))} | {metric_counts[key]:,} |"
        )
    if not mapped_targets:
        lines.append("| _None_ |  |  | 0 |")

    lines.extend(
        [
            "",
            "### B2. Missing targets",
            "",
            "| Metric | Statement | Governed raw-concept aliases | Status |",
            "|---|---|---|---|",
        ]
    )
    for target in missing_targets:
        lines.append(
            f"| `{target.metric_name}` | `{target.statement_type}` | {_cell(', '.join(target.aliases))} | `explicitly_missing` |"
        )
    if not missing_targets:
        lines.append("| _None_ |  |  |  |")

    lines.extend(
        [
            "",
            "## C. Arelle-evidence inference",
            "",
            "Inference is evaluated only for B2 targets. Scores rank candidates within this run;",
            "they are not confidence values and cannot supply a system metric without the separate approval workflow.",
            "Observation-gate rejection totals count observations; `insufficient_compatibility_evidence` counts candidate concept groups.",
            "",
            "| Missing metric | Statement | Outcome | Top candidate | Score / 10 | Target margin | Cross-target margin | Accepted / rejected observations; accessions |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in inference:
        lines.append(
            f"| `{row.target_metric}` | `{row.target_statement}` | `{row.outcome}` | `{_cell(row.top_candidate_qname or 'none')}` | {row.top_candidate_score} | {row.metric_candidate_margin} | {row.concept_target_margin} | {row.accepted_observation_count} / {row.rejected_observation_count} obs.; {row.accepted_accession_count} / {row.rejected_accession_count} accessions |"
        )
    if not inference:
        lines.append("| _No missing targets_ |  |  |  | 0 | 0 | 0 | 0 / 0 |")

    for row in inference:
        lines.extend(_inference_detail(row))

    lines.extend(_worked_traces(mapped_targets, missing_targets, metric_sources, inference))
    lines.extend(
        [
            "",
            "## D. Interpretation Boundary",
            "",
            "- Arelle supplies parsed facts, QName identity, concept metadata, relationships, and validation evidence. It does not produce universal system-metric labels.",
            "- B1 is the result of the existing deterministic hard mapper, including applicable approved repository mappings.",
            "- B2 remains explicitly missing. Section C is report-only shadow evidence and does not add candidates to the approved dictionary.",
            "- Formula suggestions and all LLM calls are intentionally not run by this experiment.",
            "- Namespace is retained for lineage and collision detection, not used as the normal target-mapping selector.",
            "- No database row, financial metric, inferred mapping, formula, or schema was created or changed.",
            "",
        ]
    )
    return "\n".join(lines)


def _proof_summary_row(proof: FilingProof) -> str:
    if proof.result is None or proof.filing is None:
        return (
            f"| {proof.requested_form} | `{proof.filing.accession_number if proof.filing else 'unavailable'}` | N | "
            f"{_cell(proof.failure_stage or 'unknown')}: {_cell(proof.failure_reason or 'unknown')} | 0 | 0 | 0 | 0 | 0 | N | 0.000 |"
        )
    precedence = apply_arelle_accession_precedence((proof.result,))
    duplicates = sum(
        DUPLICATE_FACT in item.quality_flags for item in precedence.quarantined
    )
    reason = "" if proof.result.status == "complete" else _result_reason(proof)
    return (
        f"| {proof.requested_form} | `{proof.filing.accession_number}` | "
        f"{'Y' if proof.result.status == 'complete' else 'N'} | {_cell(reason)} | "
        f"{proof.result.counts.facts:,} | {len({fact.concept_key for fact in proof.result.facts}):,} | "
        f"{len(precedence.selected):,} | {len(precedence.quarantined):,} | {duplicates:,} | "
        f"{'Y' if precedence.selected else 'N'} | {proof.result.timings.total_seconds:.3f} |"
    )


def _result_reason(proof: FilingProof) -> str:
    if proof.failure_reason:
        return proof.failure_reason
    if proof.result is None:
        return "No Arelle result"
    counts = Counter(
        diagnostic.code
        for diagnostic in proof.result.diagnostics
        if diagnostic.severity in {"error", "fatal"}
    )
    if not counts:
        return f"Arelle status {proof.result.status}"
    return "; ".join(f"{code} ({count})" for code, count in counts.most_common(5))


def _inference_detail(row: ArelleInferenceResult) -> list[str]:
    lines = [
        "",
        f"### C trace: `{row.target_metric}` ({row.target_statement})",
        "",
        f"- Outcome: `{row.outcome}` -- {row.reason}",
        f"- Top candidate: `{row.top_candidate_qname or 'none'}`",
        f"- Score categories: statement role {row.statement_role_score}/2; presentation neighborhood {row.presentation_neighborhood_score}/2; calculation/definition network {row.relationship_network_score}/2; cross-form recurrence {row.cross_form_recurrence_score}/2; governed lexical evidence {row.governed_lexical_score}/2.",
        f"- Target-to-concept margin: {row.metric_candidate_margin}; concept-to-target margin: {row.concept_target_margin}.",
        f"- Runner-up: `{row.runner_up_candidate_qname or 'none'}` ({row.runner_up_score if row.runner_up_score is not None else 'n/a'}).",
        f"- Strongest competing target: `{row.strongest_competing_target or 'none'}` ({row.strongest_competing_target_score if row.strongest_competing_target_score is not None else 'n/a'}).",
        f"- Accessions: `{', '.join(row.observed_accessions) or 'none'}`.",
    ]
    if row.hard_gates:
        lines.append(
            "- Hard gates: " + "; ".join(f"{name}={outcome}" for name, outcome in row.hard_gates) + "."
        )
    if row.citations:
        lines.append("- Evidence: " + "; ".join(_cell(value) for value in row.citations) + ".")
    if row.rejection_totals:
        lines.append(
            "- Rejections: "
            + "; ".join(f"{reason}={count}" for reason, count in row.rejection_totals)
            + "."
        )
    for reason, examples in row.rejection_examples:
        lines.append(f"- `{reason}` examples: {_cell('; '.join(examples))}")
    return lines


def _worked_traces(
    mapped_targets: tuple[CanonicalMetricTarget, ...],
    missing_targets: tuple[CanonicalMetricTarget, ...],
    metric_sources: Mapping[tuple[str, str], tuple[str, ...]],
    inference: tuple[ArelleInferenceResult, ...],
) -> list[str]:
    lines = ["", "## C1. Worked workflow traces", ""]
    if mapped_targets:
        target = mapped_targets[0]
        sources = metric_sources.get((target.metric_name, target.statement_type), ())
        lines.extend(
            [
                f"- Mapped example `{target.metric_name}`: selected Arelle observation -> normalized fact -> existing hard mapping ({_cell('; '.join(sources) or 'catalog')}) -> B1.",
            ]
        )
    if missing_targets:
        target = missing_targets[0]
        result = next(
            row
            for row in inference
            if (row.target_metric, row.target_statement)
            == (target.metric_name, target.statement_type)
        )
        lines.append(
            f"- Missing example `{target.metric_name}`: no usable hard-mapped fact -> B2 -> shadow inference `{result.outcome}` with candidate `{result.top_candidate_qname or 'none'}` -> no activation or write."
        )
    if not mapped_targets and not missing_targets:
        lines.append("- No applicable targets were available for a worked trace.")
    return lines


def _taxonomy_name(qname: QNameKey) -> str:
    if qname.prefix:
        return qname.prefix
    host = (qname.namespace_uri.split("//", 1)[-1].split("/", 1)[0]).lower()
    if host.endswith("fasb.org"):
        return "us-gaap"
    if host:
        return host.removeprefix("www.")
    return "unknown"


def _unit_text(unit: UnitKey | None) -> str:
    if unit is None:
        return "none"
    numerator = "*".join(_qname_text(item) for item in unit.numerator)
    if not unit.denominator:
        return numerator or "none"
    denominator = "*".join(_qname_text(item) for item in unit.denominator)
    return f"{numerator}/{denominator}"


def _qname_text(qname: QNameKey | None) -> str:
    if qname is None:
        return ""
    return f"{qname.prefix}:{qname.local_name}" if qname.prefix else qname.local_name


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _stage_time(session: Plan203ProofSession, stage: str) -> float:
    return sum(value for name, value in session.stage_timings if name == stage)


def _proof_order(proof: FilingProof) -> tuple[int, str]:
    complete = proof.result is not None and proof.result.status == "complete"
    return (0 if complete else 1, proof.requested_form)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(content, encoding="utf-8")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _rooted(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
