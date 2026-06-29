"""Semantic candidate generation for missing canonical financial metrics."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from llama_index.embeddings.fastembed import FastEmbedEmbedding

from src.processing.mapping_catalog import (
    IndustryFactTarget,
    all_target_facts,
    target_facts_for_industry_labels,
)
from src.processing.xbrl_normalizer import NormalizedFact

SEMANTIC_MATCH_METHOD = "semantic_candidate_embedding_v2"
DEFAULT_MINIMUM_SIMILARITY = 0.50
DEFAULT_CANDIDATES_PER_TARGET = 3


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
    """A canonical metric plus its candidate XBRL concept names."""

    metric_name: str
    statement_type: str
    aliases: tuple[str, ...]
    candidate_concepts: tuple[TargetConceptCandidate, ...]
    industry_labels: tuple[str, ...]
    required_for_core: bool
    required_for_specialized_indicators: bool


@dataclass(frozen=True)
class SemanticMappingCandidate:
    """A non-authoritative semantic mapping suggestion."""

    taxonomy: str
    concept: str
    namespace_uri: str | None
    metric_name: str
    statement_type: str
    confidence: float
    match_method: str
    evidence: dict[str, object]


@dataclass(frozen=True)
class TargetEmbeddingPrewarmResult:
    """Summary of a target XBRL concept candidate embedding prewarm run."""

    embedding_model_name: str
    cache_path: Path
    target_count: int
    target_candidate_count: int
    cached_vector_count: int
    reused_vector_count: int
    created_vector_count: int


@dataclass(frozen=True)
class _ObservedConcept:
    taxonomy: str
    concept: str
    namespace_uri: str | None
    label: str | None
    description: str | None
    units: tuple[str, ...]
    period_types: tuple[str, ...]
    accessions: tuple[str, ...]


@dataclass(frozen=True)
class _TargetEmbeddingCacheResult:
    vectors: list[list[float]]
    cached_vector_count: int
    reused_vector_count: int
    created_vector_count: int


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


def prewarm_all_target_candidate_embeddings(
    *,
    embedding_model_name: str,
    model_cache_dir: Path,
    target_embedding_path: Path,
) -> TargetEmbeddingPrewarmResult:
    """Precompute vectors for every target XBRL concept candidate in the catalog."""
    targets = all_canonical_metric_targets()
    target_candidates = _target_concept_candidates(targets)
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    embedding_model = _embedding_model(embedding_model_name, str(model_cache_dir))
    target_texts = [_target_candidate_text(target) for target in target_candidates]
    result = _load_or_create_target_embedding_cache(
        target_candidates,
        target_texts,
        embedding_model,
        embedding_model_name,
        target_embedding_path,
    )
    return TargetEmbeddingPrewarmResult(
        embedding_model_name=embedding_model_name,
        cache_path=target_embedding_path,
        target_count=len(targets),
        target_candidate_count=len(target_candidates),
        cached_vector_count=result.cached_vector_count,
        reused_vector_count=result.reused_vector_count,
        created_vector_count=result.created_vector_count,
    )


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


def generate_semantic_mapping_candidates(
    facts: Iterable[NormalizedFact],
    targets: Sequence[CanonicalMetricTarget],
    known_mapping_keys: set[tuple[str, str]],
    *,
    embedding_model_name: str,
    model_cache_dir: Path,
    target_embedding_path: Path,
    minimum_similarity: float = DEFAULT_MINIMUM_SIMILARITY,
    candidates_per_target: int = DEFAULT_CANDIDATES_PER_TARGET,
) -> tuple[SemanticMappingCandidate, ...]:
    """Rank unknown concepts for each missing target without approving them."""
    if not targets:
        return ()
    target_candidates = _target_concept_candidates(targets)
    if not target_candidates:
        return ()
    observed = _observed_concepts(facts, known_mapping_keys)
    if not observed:
        return ()
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    embedding_model = _embedding_model(
        embedding_model_name,
        str(model_cache_dir),
    )
    target_texts = [_target_candidate_text(target) for target in target_candidates]
    target_vectors = _load_or_create_target_embeddings(
        target_candidates,
        target_texts,
        embedding_model,
        embedding_model_name,
        target_embedding_path,
    )
    observed_vectors = embedding_model.get_text_embedding_batch(
        [_observed_text(concept) for concept in observed]
    )

    best_by_mapping_key: dict[
        tuple[str, str, str, str],
        tuple[float, _ObservedConcept, TargetConceptCandidate],
    ] = {}
    for target, target_vector in zip(target_candidates, target_vectors, strict=True):
        ranked: list[tuple[float, _ObservedConcept]] = []
        for concept, concept_vector in zip(observed, observed_vectors, strict=True):
            if not _period_is_compatible(target.statement_type, concept.period_types):
                continue
            similarity = _cosine_similarity(target_vector, concept_vector)
            if similarity >= minimum_similarity:
                ranked.append((similarity, concept))
        ranked.sort(key=lambda item: (-item[0], item[1].taxonomy, item[1].concept))
        for similarity, concept in ranked[:candidates_per_target]:
            key = (
                concept.taxonomy,
                concept.concept,
                target.metric_name,
                target.statement_type,
            )
            current = best_by_mapping_key.get(key)
            if current is None or similarity > current[0]:
                best_by_mapping_key[key] = (similarity, concept, target)
    candidates = [
        SemanticMappingCandidate(
            taxonomy=concept.taxonomy,
            concept=concept.concept,
            namespace_uri=concept.namespace_uri,
            metric_name=target.metric_name,
            statement_type=target.statement_type,
            confidence=round(similarity, 6),
            match_method=SEMANTIC_MATCH_METHOD,
            evidence={
                "candidate_is_authoritative": False,
                "embedding_granularity": "target_xbrl_concept_candidate",
                "target_candidate_taxonomy": target.taxonomy,
                "target_candidate_xbrl_concept": target.concept,
                "target_metric_name": target.metric_name,
                "target_statement_type": target.statement_type,
                "target_candidate_industry_labels": list(target.industry_labels),
                "observed_label": concept.label,
                "observed_description": concept.description,
                "observed_units": list(concept.units),
                "observed_period_types": list(concept.period_types),
                "source_accessions": list(concept.accessions),
                "semantic_similarity": round(similarity, 6),
                "period_compatible": True,
                "requires_review": True,
            },
        )
        for similarity, concept, target in best_by_mapping_key.values()
    ]
    candidates.sort(
        key=lambda candidate: (
            -candidate.confidence,
            candidate.metric_name,
            str(candidate.evidence.get("target_candidate_xbrl_concept", "")),
            candidate.taxonomy,
            candidate.concept,
        )
    )
    return tuple(candidates)


def _observed_concepts(
    facts: Iterable[NormalizedFact],
    known_mapping_keys: set[tuple[str, str]],
) -> tuple[_ObservedConcept, ...]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for fact in facts:
        key = (fact.taxonomy, fact.concept)
        if (
            key in known_mapping_keys
            or not fact.is_consolidated
            or fact.value is None
            or fact.is_numeric is False
        ):
            continue
        row = grouped.setdefault(
            key,
            {
                "namespace_uri": fact.namespace_uri,
                "label": fact.label,
                "description": fact.description,
                "units": set(),
                "period_types": set(),
                "accessions": set(),
            },
        )
        if not row["label"] and fact.label:
            row["label"] = fact.label
        if not row["description"] and fact.description:
            row["description"] = fact.description
        if not row["namespace_uri"] and fact.namespace_uri:
            row["namespace_uri"] = fact.namespace_uri
        row["units"].add(fact.unit)
        row["period_types"].add(fact.period_type)
        if fact.accession_number:
            row["accessions"].add(fact.accession_number)
    return tuple(
        _ObservedConcept(
            taxonomy=taxonomy,
            concept=concept,
            namespace_uri=row["namespace_uri"],
            label=row["label"],
            description=row["description"],
            units=tuple(sorted(row["units"])),
            period_types=tuple(sorted(row["period_types"])),
            accessions=tuple(sorted(row["accessions"])),
        )
        for (taxonomy, concept), row in sorted(grouped.items())
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
        industry_labels=tuple(
            sorted({*current.industry_labels, *industry_labels})
        ),
        required_for_core=current.required_for_core or required_for_core,
        required_for_specialized_indicators=(
            current.required_for_specialized_indicators
            or required_for_specialized_indicators
        ),
    )


def _target_concept_candidates(
    targets: Sequence[CanonicalMetricTarget],
) -> tuple[TargetConceptCandidate, ...]:
    return tuple(
        candidate
        for target in targets
        for candidate in target.candidate_concepts
    )


@lru_cache(maxsize=4)
def _embedding_model(
    model_name: str,
    cache_dir: str,
) -> FastEmbedEmbedding:
    return FastEmbedEmbedding(
        model_name=model_name,
        cache_dir=cache_dir,
        doc_embed_type="passage",
        embed_batch_size=256,
    )


def _load_or_create_target_embeddings(
    targets: Sequence[TargetConceptCandidate],
    target_texts: Sequence[str],
    embedding_model: FastEmbedEmbedding,
    embedding_model_name: str,
    target_embedding_path: Path,
) -> list[list[float]]:
    return _load_or_create_target_embedding_cache(
        targets,
        target_texts,
        embedding_model,
        embedding_model_name,
        target_embedding_path,
    ).vectors


def _load_or_create_target_embedding_cache(
    targets: Sequence[TargetConceptCandidate],
    target_texts: Sequence[str],
    embedding_model: FastEmbedEmbedding,
    embedding_model_name: str,
    target_embedding_path: Path,
) -> _TargetEmbeddingCacheResult:
    cached_vectors: dict[str, object] = {}
    if target_embedding_path.exists():
        try:
            payload = json.loads(target_embedding_path.read_text(encoding="utf-8"))
            if payload.get("embedding_model") == embedding_model_name:
                stored = payload.get("vectors_by_target_candidate")
                if isinstance(stored, dict):
                    cached_vectors = stored
        except (OSError, json.JSONDecodeError):
            pass

    vectors: list[list[float] | None] = [None] * len(targets)
    missing_indexes: list[int] = []
    missing_texts: list[str] = []
    reused_count = 0
    for index, (target, text) in enumerate(zip(targets, target_texts, strict=True)):
        key = _target_cache_key(target)
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = cached_vectors.get(key)
        if (
            isinstance(cached, dict)
            and cached.get("text_sha256") == text_sha256
            and isinstance(cached.get("vector"), list)
        ):
            vectors[index] = cached["vector"]
            reused_count += 1
            continue
        missing_indexes.append(index)
        missing_texts.append(text)

    if missing_texts:
        created_vectors = embedding_model.get_text_embedding_batch(missing_texts)
        for index, vector in zip(missing_indexes, created_vectors, strict=True):
            target = targets[index]
            text = target_texts[index]
            vectors[index] = vector
            cached_vectors[_target_cache_key(target)] = {
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "vector": vector,
            }

    target_embedding_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "embedding_model": embedding_model_name,
        "embedding_granularity": "target_xbrl_concept_candidate",
        "vectors_by_target_candidate": cached_vectors,
    }
    temporary_path = target_embedding_path.with_suffix(
        f"{target_embedding_path.suffix}.tmp"
    )
    temporary_path.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary_path, target_embedding_path)
    completed_vectors: list[list[float]] = []
    for vector in vectors:
        if vector is None:
            raise RuntimeError("Target embedding cache did not produce all vectors")
        completed_vectors.append(vector)
    return _TargetEmbeddingCacheResult(
        vectors=completed_vectors,
        cached_vector_count=len(cached_vectors),
        reused_vector_count=reused_count,
        created_vector_count=len(missing_texts),
    )


def _target_cache_key(target: TargetConceptCandidate) -> str:
    return (
        f"{target.metric_name}:{target.statement_type}:"
        f"{target.taxonomy}:{target.concept}"
    )


def _target_candidate_text(target: TargetConceptCandidate) -> str:
    return (
        f"Canonical financial metric: {_split_identifier(target.metric_name)}. "
        f"Financial statement: {target.statement_type}. "
        f"Candidate SEC XBRL concept: {target.concept}. "
        f"Candidate words: {_split_identifier(target.concept)}."
    )


def _observed_text(concept: _ObservedConcept) -> str:
    return " ".join(
        part
        for part in (
            f"Observed XBRL concept: {_split_identifier(concept.concept)}.",
            f"Label: {concept.label}." if concept.label else "",
            f"Definition: {concept.description}." if concept.description else "",
        )
        if part
    )


def _split_identifier(value: str) -> str:
    output: list[str] = []
    previous = ""
    for character in value.replace("_", " "):
        if previous and character.isupper() and previous.islower():
            output.append(" ")
        output.append(character)
        previous = character
    return "".join(output).lower()


def _period_is_compatible(
    statement_type: str,
    period_types: tuple[str, ...],
) -> bool:
    expected = {
        "balance_sheet": "instant",
        "income_statement": "duration",
        "cash_flow": "duration",
    }.get(statement_type)
    return expected is None or expected in period_types


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
