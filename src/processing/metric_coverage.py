"""Metric-first coverage resolution for XBRL mapping review."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.processing.formula_proposals import (
    PROVIDER_STATUS_NO_FORMULA,
    PROVIDER_STATUS_PROPOSED,
    PROVIDER_STATUS_TARGET_ZERO,
    VALIDATION_STATUS_VALIDATED,
    VALIDATION_STATUS_ZERO_EVIDENCE,
)
from src.processing.mapping_catalog import (
    STATUS_FOUND_MAPPED,
    STATUS_FOUND_MAPPED_ALTERNATE,
    STATUS_FOUND_UNMAPPED,
    STATUS_MISSING_TARGET,
)

METRIC_COVERAGE_MAPPED = "mapped"
METRIC_COVERAGE_APPROVED_ALTERNATE = "covered_by_approved_alternate"
METRIC_COVERAGE_NEEDS_LLM_RESOLUTION = "needs_llm_resolution"
METRIC_COVERAGE_NO_EVIDENCE = "no_evidence"

REVIEW_ACTION_NONE = "none"
REVIEW_ACTION_LLM_CHOICE = "llm_choose_mapping_formula_or_zero"
REVIEW_ACTION_NO_EVIDENCE = "no_evidence_to_review"

RESOLUTION_OPTION_FORMULA = "formula_from_raw_concepts"
RESOLUTION_OPTION_ZERO = "zero_target"


@dataclass(frozen=True)
class MetricCoverageResolution:
    """One metric-level coverage decision surface for mapping review."""

    metric_name: str
    statement_type: str
    coverage_status: str
    reviewer_action: str
    llm_choice_options: tuple[str, ...]
    target_xbrl_concepts: tuple[str, ...]
    mapped_target_concepts: tuple[str, ...]
    missing_target_concepts: tuple[str, ...]
    found_unmapped_target_concepts: tuple[str, ...]
    approved_alternate_concepts: tuple[str, ...]
    formula_proposal_count: int
    validated_formula_count: int
    zero_proposal_count: int
    validated_zero_count: int
    no_formula_count: int
    notes: str


def resolve_metric_coverage(
    *,
    target_coverage_rows: Sequence[Mapping[str, Any]],
    formula_diagnostic_rows: Sequence[Mapping[str, Any]] = (),
) -> tuple[MetricCoverageResolution, ...]:
    """Collapse tag-level coverage evidence into one row per internal metric.

    The resolver does not approve mappings, formulas, or zero-target decisions.
    It only prepares the metric-level evidence packet that a reviewer or LLM can
    use to choose between formula review or zero review.
    """

    target_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in target_coverage_rows:
        key = _metric_key(
            metric_name=row.get("internal_metric_name"),
            statement_type=row.get("statement_type"),
        )
        if key[0]:
            target_groups[key].append(row)

    formula_by_metric = _group_rows_by_metric(
        formula_diagnostic_rows,
        metric_name_key="target_metric_name",
        statement_type_key="target_primary_statement",
    )

    resolutions: list[MetricCoverageResolution] = []
    for key in sorted(target_groups):
        metric_name, statement_type = key
        target_rows = target_groups[key]
        formula_rows = formula_by_metric.get(key, ())
        mapped_targets = _concepts_with_status(target_rows, STATUS_FOUND_MAPPED)
        alternate_targets = _concepts_with_status(
            target_rows,
            STATUS_FOUND_MAPPED_ALTERNATE,
        )
        found_unmapped_targets = _concepts_with_status(
            target_rows,
            STATUS_FOUND_UNMAPPED,
        )
        missing_targets = _concepts_with_status(target_rows, STATUS_MISSING_TARGET)
        approved_alternates = _approved_alternate_concepts(target_rows)
        formula_count = _count_formula_proposals(formula_rows)
        validated_formula_count = _count_rows(
            formula_rows,
            key="validation_status",
            value=VALIDATION_STATUS_VALIDATED,
        )
        zero_count = _count_rows(
            formula_rows,
            key="provider_status",
            value=PROVIDER_STATUS_TARGET_ZERO,
        )
        validated_zero_count = _count_rows(
            formula_rows,
            key="validation_status",
            value=VALIDATION_STATUS_ZERO_EVIDENCE,
        )
        no_formula_count = _count_rows(
            formula_rows,
            key="provider_status",
            value=PROVIDER_STATUS_NO_FORMULA,
        )
        status, action, options, notes = _resolution_decision(
            mapped_target_count=len(mapped_targets),
            approved_alternate_count=len(approved_alternates) or len(alternate_targets),
            formula_proposal_count=formula_count,
            validated_formula_count=validated_formula_count,
            zero_proposal_count=zero_count,
            validated_zero_count=validated_zero_count,
            found_unmapped_target_count=len(found_unmapped_targets),
            missing_target_count=len(missing_targets),
        )
        resolutions.append(
            MetricCoverageResolution(
                metric_name=metric_name,
                statement_type=statement_type,
                coverage_status=status,
                reviewer_action=action,
                llm_choice_options=options,
                target_xbrl_concepts=_sorted_unique(
                    _text(row.get("target_xbrl_concept")) for row in target_rows
                ),
                mapped_target_concepts=mapped_targets,
                missing_target_concepts=missing_targets,
                found_unmapped_target_concepts=found_unmapped_targets,
                approved_alternate_concepts=approved_alternates,
                formula_proposal_count=formula_count,
                validated_formula_count=validated_formula_count,
                zero_proposal_count=zero_count,
                validated_zero_count=validated_zero_count,
                no_formula_count=no_formula_count,
                notes=notes,
            )
        )
    return tuple(resolutions)


def metric_coverage_report_rows(
    resolutions: Iterable[MetricCoverageResolution],
) -> list[dict[str, object]]:
    """Return compact rows for Markdown/CSV-style inspection reports."""

    return [
        {
            "internal_metric_name": resolution.metric_name,
            "statement_type": resolution.statement_type,
            "coverage_status": resolution.coverage_status,
            "reviewer_action": resolution.reviewer_action,
            "llm_choice_options": _join(resolution.llm_choice_options),
            "target_xbrl_concepts": _join(resolution.target_xbrl_concepts),
            "mapped_target_concepts": _join(resolution.mapped_target_concepts),
            "approved_alternate_concepts": _join(resolution.approved_alternate_concepts),
            "formula_evidence": (
                f"proposed={resolution.formula_proposal_count}; "
                f"validated={resolution.validated_formula_count}; "
                f"no_formula={resolution.no_formula_count}"
            ),
            "zero_evidence": (
                f"proposed={resolution.zero_proposal_count}; "
                f"validated={resolution.validated_zero_count}"
            ),
            "notes": resolution.notes,
        }
        for resolution in resolutions
    ]


def _resolution_decision(
    *,
    mapped_target_count: int,
    approved_alternate_count: int,
    formula_proposal_count: int,
    validated_formula_count: int,
    zero_proposal_count: int,
    validated_zero_count: int,
    found_unmapped_target_count: int,
    missing_target_count: int,
) -> tuple[str, str, tuple[str, ...], str]:
    if mapped_target_count:
        return (
            METRIC_COVERAGE_MAPPED,
            REVIEW_ACTION_NONE,
            (),
            "Approved/catalog mapping already creates financial_metrics rows.",
        )
    if approved_alternate_count:
        return (
            METRIC_COVERAGE_APPROVED_ALTERNATE,
            REVIEW_ACTION_NONE,
            (),
            "Metric is covered by an approved alternate concept; exact target tags remain absent.",
        )

    options: list[str] = []
    if formula_proposal_count or validated_formula_count or found_unmapped_target_count:
        options.append(RESOLUTION_OPTION_FORMULA)
    if zero_proposal_count or validated_zero_count:
        options.append(RESOLUTION_OPTION_ZERO)
    options = list(dict.fromkeys(options))
    if options:
        return (
            METRIC_COVERAGE_NEEDS_LLM_RESOLUTION,
            REVIEW_ACTION_LLM_CHOICE,
            tuple(options),
            "Ask the LLM/reviewer to choose one resolution path; do not persist without approval.",
        )

    missing_note = (
        f"{missing_target_count} target concepts missing"
        if missing_target_count
        else "no mapped or reviewable target evidence"
    )
    return (
        METRIC_COVERAGE_NO_EVIDENCE,
        REVIEW_ACTION_NO_EVIDENCE,
        (),
        f"{missing_note}; leave the metric unavailable until new evidence appears.",
    )


def _group_rows_by_metric(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric_name_key: str,
    statement_type_key: str,
) -> dict[tuple[str, str], tuple[Mapping[str, Any], ...]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _metric_key(
            metric_name=row.get(metric_name_key),
            statement_type=row.get(statement_type_key),
        )
        if key[0]:
            grouped[key].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _metric_key(*, metric_name: object, statement_type: object) -> tuple[str, str]:
    return (_text(metric_name), _text(statement_type))


def _concepts_with_status(
    rows: Sequence[Mapping[str, Any]],
    status: str,
) -> tuple[str, ...]:
    return _sorted_unique(
        _text(row.get("target_xbrl_concept"))
        for row in rows
        if _text(row.get("status")) == status
    )


def _approved_alternate_concepts(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    concepts: list[str] = []
    for row in rows:
        if _text(row.get("status")) != STATUS_FOUND_MAPPED_ALTERNATE:
            continue
        concepts.extend(_split_concepts(row.get("alternate_mapped_concepts")))
    return _sorted_unique(concepts)


def _count_formula_proposals(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if _text(row.get("provider_status")) == PROVIDER_STATUS_PROPOSED
    )


def _count_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
    value: str,
) -> int:
    return sum(1 for row in rows if _text(row.get(key)) == value)


def _split_concepts(value: object) -> tuple[str, ...]:
    text = _text(value)
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _join(values: Sequence[str]) -> str:
    return ", ".join(values)


def _text(value: object) -> str:
    return str(value or "").strip()
