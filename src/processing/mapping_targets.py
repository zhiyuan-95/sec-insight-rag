"""Canonical metric target helpers for hard-mapping coverage checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from src.processing.mapping_catalog import (
    IndustryFactTarget,
    all_target_facts,
    target_facts_for_industry_labels,
)
from src.processing.xbrl_normalizer import NormalizedFact


@dataclass(frozen=True)
class TargetConceptCandidate:
    """One target XBRL concept candidate for a canonical financial metric."""

    taxonomy: str
    concept: str
    metric_name: str
    statement_type: str
    industry_labels: tuple[str, ...]
    required_for_core: bool
    required_for_specialized_indicators: bool


@dataclass(frozen=True)
class CanonicalMetricTarget:
    """A canonical metric plus its catalog XBRL concept names."""

    metric_name: str
    statement_type: str
    aliases: tuple[str, ...]
    candidate_concepts: tuple[TargetConceptCandidate, ...]
    industry_labels: tuple[str, ...]
    required_for_core: bool
    required_for_specialized_indicators: bool


def canonical_metric_targets(
    industry_labels: Iterable[str],
) -> tuple[CanonicalMetricTarget, ...]:
    """Collapse raw aliases into one definition per canonical metric."""
    return _canonical_metric_targets_from_facts(
        target_facts_for_industry_labels(industry_labels)
    )


def all_canonical_metric_targets() -> tuple[CanonicalMetricTarget, ...]:
    """Return canonical metric targets across common base and all industry bundles."""
    return _canonical_metric_targets_from_facts(all_target_facts())


def missing_metric_targets(
    facts: Iterable[NormalizedFact],
    targets: Iterable[CanonicalMetricTarget],
    mappings: Mapping[tuple[str, str], str],
) -> tuple[CanonicalMetricTarget, ...]:
    """Return targets with no usable consolidated mapped source fact."""
    found_metrics = {
        mappings[(fact.taxonomy, fact.concept)]
        for fact in facts
        if fact.is_consolidated
        and fact.value is not None
        and (fact.taxonomy, fact.concept) in mappings
    }
    return tuple(target for target in targets if target.metric_name not in found_metrics)


def _canonical_metric_targets_from_facts(
    target_facts: Iterable[IndustryFactTarget],
) -> tuple[CanonicalMetricTarget, ...]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for target in target_facts:
        key = (target.internal_metric_name, target.statement_type)
        row = grouped.setdefault(
            key,
            {
                "aliases": [],
                "candidate_concepts": {},
                "industry_labels": [],
                "required_for_core": False,
                "required_for_specialized_indicators": False,
            },
        )
        aliases = row["aliases"]
        if isinstance(aliases, list) and target.raw_concept not in aliases:
            aliases.append(target.raw_concept)
        split_labels = _split_industry_labels(target.industry_label)
        labels = row["industry_labels"]
        if isinstance(labels, list):
            for label in split_labels:
                if label not in labels:
                    labels.append(label)
        candidates = row["candidate_concepts"]
        if isinstance(candidates, dict):
            _merge_target_concept_candidate(
                candidates,
                target.taxonomy,
                target.raw_concept,
                target.internal_metric_name,
                target.statement_type,
                split_labels,
                target.required_for_core,
                target.required_for_specialized_indicators,
            )
        row["required_for_core"] = bool(
            row["required_for_core"] or target.required_for_core
        )
        row["required_for_specialized_indicators"] = bool(
            row["required_for_specialized_indicators"]
            or target.required_for_specialized_indicators
        )
    return tuple(
        CanonicalMetricTarget(
            metric_name=metric_name,
            statement_type=statement_type,
            aliases=tuple(sorted(row["aliases"])),
            candidate_concepts=tuple(
                sorted(
                    row["candidate_concepts"].values(),
                    key=lambda candidate: (candidate.taxonomy, candidate.concept),
                )
            ),
            industry_labels=tuple(sorted(row["industry_labels"])),
            required_for_core=bool(row["required_for_core"]),
            required_for_specialized_indicators=bool(
                row["required_for_specialized_indicators"]
            ),
        )
        for (metric_name, statement_type), row in sorted(grouped.items())
    )


def _split_industry_labels(value: str) -> tuple[str, ...]:
    return tuple(label for label in value.split(", ") if label)


def _merge_target_concept_candidate(
    candidates: dict[tuple[str, str], TargetConceptCandidate],
    taxonomy: str,
    concept: str,
    metric_name: str,
    statement_type: str,
    industry_labels: tuple[str, ...],
    required_for_core: bool,
    required_for_specialized_indicators: bool,
) -> None:
    key = (taxonomy, concept)
    current = candidates.get(key)
    if current is None:
        candidates[key] = TargetConceptCandidate(
            taxonomy=taxonomy,
            concept=concept,
            metric_name=metric_name,
            statement_type=statement_type,
            industry_labels=tuple(sorted(industry_labels)),
            required_for_core=required_for_core,
            required_for_specialized_indicators=required_for_specialized_indicators,
        )
        return
    candidates[key] = TargetConceptCandidate(
        taxonomy=current.taxonomy,
        concept=current.concept,
        metric_name=current.metric_name,
        statement_type=current.statement_type,
        industry_labels=tuple(sorted({*current.industry_labels, *industry_labels})),
        required_for_core=current.required_for_core or required_for_core,
        required_for_specialized_indicators=(
            current.required_for_specialized_indicators
            or required_for_specialized_indicators
        ),
    )
