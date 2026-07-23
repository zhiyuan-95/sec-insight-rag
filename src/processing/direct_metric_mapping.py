"""Direct metric mapping over precedence-selected annual observations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.processing.accession_precedence import (
    CompanyPrecedenceResult,
    PrecedenceSelectedObservation,
)
from src.processing.base_metrics import BaseMetricRecord
from src.processing.mapping_targets import CanonicalMetricTarget


@dataclass(frozen=True)
class DirectMappingRejection:
    """One known direct mapping rejected by a compatibility safeguard."""

    raw_fact_id: int
    taxonomy: str
    concept: str
    metric_name: str
    reason: str
    mapping_origin: str
    mapping_id: int | None


@dataclass(frozen=True)
class DirectConceptMapping:
    """One active reviewed concept-to-metric mapping."""

    taxonomy: str
    concept: str
    metric_name: str
    statement_type: str
    mapping_id: int | None = None
    consolidated_or_segment: str = "consolidated"


@dataclass(frozen=True)
class ShadowMappingCandidate:
    """One inspectable deterministic suggestion that cannot create a metric."""

    raw_fact_id: int
    taxonomy: str
    concept: str
    metric_name: str
    statement_type: str
    score: float
    match_method: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class DirectMetricMappingLineage:
    """The approved decision that allowed one direct metric mapping."""

    raw_fact_id: int
    metric_name: str
    mapping_origin: str
    mapping_id: int | None


@dataclass(frozen=True)
class _ResolvedDirectMapping:
    target: CanonicalMetricTarget
    consolidated_or_segment: str
    priority: int
    mapping_origin: str
    mapping_id: int | None


@dataclass(frozen=True)
class PeriodMetricMappingResult:
    """Direct metrics and exact remaining targets for one fiscal period."""

    direct_metrics: tuple[BaseMetricRecord, ...]
    direct_mapping_lineage: tuple[DirectMetricMappingLineage, ...]
    compatibility_rejections: tuple[DirectMappingRejection, ...]
    shadow_candidates: tuple[ShadowMappingCandidate, ...]
    missing_targets: tuple[CanonicalMetricTarget, ...]


def map_precedence_selected_period(
    *,
    precedence: CompanyPrecedenceResult,
    fiscal_year: int,
    fiscal_period: str,
    targets: Sequence[CanonicalMetricTarget],
    approved_mappings: Sequence[DirectConceptMapping] = (),
) -> PeriodMetricMappingResult:
    """Map selected observations and return only targets still unresolved."""
    target_by_concept: dict[tuple[str, str], _ResolvedDirectMapping] = {}
    for target in targets:
        for candidate in target.candidate_concepts:
            key = (candidate.taxonomy.casefold(), candidate.concept)
            proposed = _ResolvedDirectMapping(
                target=target,
                consolidated_or_segment=candidate.consolidated_or_segment,
                priority=candidate.priority,
                mapping_origin="source_controlled",
                mapping_id=None,
            )
            current = target_by_concept.get(key)
            if current is None or _direct_mapping_priority(
                proposed
            ) < _direct_mapping_priority(current):
                target_by_concept[key] = proposed
    targets_by_key = {
        (target.metric_name, target.statement_type): target for target in targets
    }
    for mapping in approved_mappings:
        target = targets_by_key.get(
            (mapping.metric_name, mapping.statement_type)
        )
        if target is not None:
            target_by_concept.setdefault(
                (mapping.taxonomy.casefold(), mapping.concept),
                _ResolvedDirectMapping(
                    target=target,
                    consolidated_or_segment=mapping.consolidated_or_segment,
                    priority=-1,
                    mapping_origin="approved",
                    mapping_id=mapping.mapping_id,
                ),
            )
    metrics: list[BaseMetricRecord] = []
    lineage: list[DirectMetricMappingLineage] = []
    rejections: list[DirectMappingRejection] = []
    for selected in precedence.selected_observations:
        fact = selected.observation.fact
        if fact.fiscal_year != fiscal_year or fact.fiscal_period != fiscal_period:
            continue
        mapping = target_by_concept.get((fact.taxonomy.casefold(), fact.concept))
        if mapping is None:
            continue
        rejection_reason = _compatibility_rejection_reason(
            selected=selected,
            target=mapping.target,
            consolidated_or_segment=mapping.consolidated_or_segment,
        )
        if rejection_reason is not None:
            rejections.append(
                DirectMappingRejection(
                    raw_fact_id=selected.observation.raw_fact_id,
                    taxonomy=fact.taxonomy,
                    concept=fact.concept,
                    metric_name=mapping.target.metric_name,
                    reason=rejection_reason,
                    mapping_origin=mapping.mapping_origin,
                    mapping_id=mapping.mapping_id,
                )
            )
            continue
        metrics.append(
            BaseMetricRecord(
                raw_fact_id=selected.observation.raw_fact_id,
                accession_number=selected.accession_number,
                statement_type=mapping.target.statement_type,
                metric_name=mapping.target.metric_name,
                value_numeric=fact.value,
                value_raw=fact.value_raw,
                unit=fact.unit,
                period_type=fact.period_type,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period,
                start_date=fact.start_date,
                end_date=fact.end_date,
                filing_date=selected.filing_date,
                is_active_window=True,
            )
        )
        lineage.append(
            DirectMetricMappingLineage(
                raw_fact_id=selected.observation.raw_fact_id,
                metric_name=mapping.target.metric_name,
                mapping_origin=mapping.mapping_origin,
                mapping_id=mapping.mapping_id,
            )
        )
    mapped_names = {metric.metric_name for metric in metrics}
    missing_targets = tuple(
        target for target in targets if target.metric_name not in mapped_names
    )
    return PeriodMetricMappingResult(
        direct_metrics=tuple(metrics),
        direct_mapping_lineage=tuple(lineage),
        compatibility_rejections=tuple(rejections),
        shadow_candidates=_infer_shadow_candidates(
            precedence=precedence,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            missing_targets=missing_targets,
            known_mapping_keys=set(target_by_concept),
        ),
        missing_targets=missing_targets,
    )


def _compatibility_rejection_reason(
    *,
    selected: PrecedenceSelectedObservation,
    target: CanonicalMetricTarget,
    consolidated_or_segment: str,
) -> str | None:
    fact = selected.observation.fact
    if fact.value is None:
        return "numeric_value_unavailable"
    if fact.is_numeric is False:
        return "source_not_numeric"
    expected_period_type = _target_period_type(target)
    if expected_period_type is not None and fact.period_type != expected_period_type:
        return "incompatible_period_type"
    if _fact_unit_family(fact.unit) != _target_unit_family(target):
        return "incompatible_unit_family"
    if consolidated_or_segment == "consolidated" and (
        not fact.is_consolidated or fact.dimensions
    ):
        return "unusable_dimensional_context"
    arelle_fact_id = selected.observation.arelle_fact_id
    if arelle_fact_id is not None and any(
        arelle_fact_id in diagnostic.fact_ids
        and diagnostic.severity.casefold() in {"error", "critical", "fatal"}
        for diagnostic in selected.reconciliation.blocking_diagnostics
    ):
        return "blocking_diagnostic"
    return None


def _target_period_type(target: CanonicalMetricTarget) -> str | None:
    if target.statement_type == "balance_sheet":
        return "instant"
    if target.statement_type in {
        "cash_flow",
        "cash_flow_statement",
        "income_statement",
        "shares",
    }:
        return "duration"
    return None


def _target_unit_family(target: CanonicalMetricTarget) -> str:
    metric_name = target.metric_name.casefold()
    aliases = tuple(alias.casefold() for alias in target.aliases)
    if metric_name.endswith("eps") or any(
        "earningspershare" in alias for alias in aliases
    ):
        return "per_share"
    if "shares" in metric_name or target.statement_type == "shares":
        return "shares"
    return "monetary"


def _fact_unit_family(unit: str) -> str:
    normalized = unit.strip().casefold()
    if "/" in normalized and "share" in normalized:
        return "per_share"
    if normalized in {"share", "shares"}:
        return "shares"
    currency = normalized.rsplit(":", 1)[-1]
    if "/" not in normalized and len(currency) == 3 and currency.isalpha():
        return "monetary"
    return "other"


def _infer_shadow_candidates(
    *,
    precedence: CompanyPrecedenceResult,
    fiscal_year: int,
    fiscal_period: str,
    missing_targets: Sequence[CanonicalMetricTarget],
    known_mapping_keys: set[tuple[str, str]],
) -> tuple[ShadowMappingCandidate, ...]:
    metadata_by_concept = {
        (item.identity.taxonomy.casefold(), item.identity.concept): item
        for item in precedence.concept_metadata
    }
    candidates: list[ShadowMappingCandidate] = []
    for target in missing_targets:
        ranked: list[ShadowMappingCandidate] = []
        target_tokens = _semantic_tokens(
            " ".join((target.metric_name, *target.aliases))
        )
        for selected in precedence.selected_observations:
            fact = selected.observation.fact
            key = (fact.taxonomy.casefold(), fact.concept)
            if (
                fact.fiscal_year != fiscal_year
                or fact.fiscal_period != fiscal_period
                or key in known_mapping_keys
                or _compatibility_rejection_reason(
                    selected=selected,
                    target=target,
                    consolidated_or_segment="consolidated",
                )
                is not None
            ):
                continue
            metadata = metadata_by_concept.get(key)
            if metadata is None:
                continue
            fields = {
                field.name: field
                for field in metadata.fields
                if isinstance(field.value, str)
                and field.source_system == "arelle_structural"
            }
            if not fields:
                continue
            label = fields.get("label")
            description = fields.get("description")
            observed_tokens = _semantic_tokens(
                " ".join(
                    part
                    for part in (
                        fact.concept,
                        str(label.value) if label is not None else "",
                        (
                            str(description.value)
                            if description is not None
                            else ""
                        ),
                    )
                    if part
                )
            )
            overlap = target_tokens & observed_tokens
            if not overlap:
                continue
            score = round(
                len(overlap) / len(target_tokens | observed_tokens),
                6,
            )
            ranked.append(
                ShadowMappingCandidate(
                    raw_fact_id=selected.observation.raw_fact_id,
                    taxonomy=fact.taxonomy,
                    concept=fact.concept,
                    metric_name=target.metric_name,
                    statement_type=target.statement_type,
                    score=score,
                    match_method="arelle_lexical_shadow_v1",
                    evidence={
                        "candidate_is_authoritative": False,
                        "requires_review": True,
                        "target_aliases": list(target.aliases),
                        "observed_label": (
                            label.value if label is not None else None
                        ),
                        "observed_description": (
                            description.value
                            if description is not None
                            else None
                        ),
                        "metadata_sources": [
                            {
                                "field": field.name,
                                "source_system": field.source_system,
                                "source_accession_number": (
                                    field.source_accession_number
                                ),
                            }
                            for field in metadata.fields
                            if field.name in {"label", "description"}
                            and field.source_system == "arelle_structural"
                        ],
                        "overlapping_terms": sorted(overlap),
                        "lexical_score": score,
                    },
                )
            )
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.taxonomy.casefold(),
                item.concept,
                item.raw_fact_id,
            )
        )
        candidates.extend(ranked[:3])
    return tuple(candidates)


def _semantic_tokens(value: str) -> set[str]:
    split_identifier = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return {
        token
        for token in re.findall(r"[a-z0-9]+", split_identifier.casefold())
        if len(token) > 1
    }


def _direct_mapping_priority(
    mapping: _ResolvedDirectMapping,
) -> tuple[int, str, str]:
    return (
        mapping.priority,
        mapping.target.metric_name,
        mapping.target.statement_type,
    )
