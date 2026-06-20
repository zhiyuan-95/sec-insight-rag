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

from src.processing.mapping_catalog import target_facts_for_industry_labels
from src.processing.xbrl_normalizer import NormalizedFact

SEMANTIC_MATCH_METHOD = "semantic_embedding_v1"
DEFAULT_MINIMUM_SIMILARITY = 0.50
DEFAULT_CANDIDATES_PER_TARGET = 3


@dataclass(frozen=True)
class CanonicalMetricTarget:
    """A canonical metric plus the reviewed aliases used to describe it."""

    metric_name: str
    statement_type: str
    aliases: tuple[str, ...]
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
class _ObservedConcept:
    taxonomy: str
    concept: str
    namespace_uri: str | None
    label: str | None
    description: str | None
    units: tuple[str, ...]
    period_types: tuple[str, ...]
    accessions: tuple[str, ...]


def canonical_metric_targets(
    industry_labels: Iterable[str],
) -> tuple[CanonicalMetricTarget, ...]:
    """Collapse raw aliases into one definition per canonical metric."""
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for target in target_facts_for_industry_labels(industry_labels):
        key = (target.internal_metric_name, target.statement_type)
        row = grouped.setdefault(
            key,
            {
                "aliases": [],
                "industry_labels": [],
                "required_for_core": False,
                "required_for_specialized_indicators": False,
            },
        )
        aliases = row["aliases"]
        if isinstance(aliases, list) and target.raw_concept not in aliases:
            aliases.append(target.raw_concept)
        labels = row["industry_labels"]
        if isinstance(labels, list):
            for label in target.industry_label.split(", "):
                if label not in labels:
                    labels.append(label)
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
    observed = _observed_concepts(facts, known_mapping_keys)
    if not observed:
        return ()
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    embedding_model = _embedding_model(
        embedding_model_name,
        str(model_cache_dir),
    )
    target_texts = [_target_text(target) for target in targets]
    target_vectors = _load_or_create_target_embeddings(
        targets,
        target_texts,
        embedding_model,
        embedding_model_name,
        target_embedding_path,
    )
    observed_vectors = embedding_model.get_text_embedding_batch(
        [_observed_text(concept) for concept in observed]
    )

    candidates: list[SemanticMappingCandidate] = []
    for target, target_vector in zip(targets, target_vectors, strict=True):
        ranked: list[tuple[float, _ObservedConcept]] = []
        for concept, concept_vector in zip(observed, observed_vectors, strict=True):
            if not _period_is_compatible(target.statement_type, concept.period_types):
                continue
            similarity = _cosine_similarity(target_vector, concept_vector)
            if similarity >= minimum_similarity:
                ranked.append((similarity, concept))
        ranked.sort(key=lambda item: (-item[0], item[1].taxonomy, item[1].concept))
        for similarity, concept in ranked[:candidates_per_target]:
            candidates.append(
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
                        "target_aliases": list(target.aliases),
                        "target_industry_labels": list(target.industry_labels),
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
    targets: Sequence[CanonicalMetricTarget],
    target_texts: Sequence[str],
    embedding_model: FastEmbedEmbedding,
    embedding_model_name: str,
    target_embedding_path: Path,
) -> list[list[float]]:
    cached_vectors: dict[str, object] = {}
    if target_embedding_path.exists():
        try:
            payload = json.loads(target_embedding_path.read_text(encoding="utf-8"))
            if payload.get("embedding_model") == embedding_model_name:
                stored = payload.get("vectors_by_target")
                if isinstance(stored, dict):
                    cached_vectors = stored
        except (OSError, json.JSONDecodeError):
            pass

    vectors: list[list[float] | None] = [None] * len(targets)
    missing_indexes: list[int] = []
    missing_texts: list[str] = []
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
        "vectors_by_target": cached_vectors,
    }
    temporary_path = target_embedding_path.with_suffix(
        f"{target_embedding_path.suffix}.tmp"
    )
    temporary_path.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary_path, target_embedding_path)
    return [vector for vector in vectors if vector is not None]


def _target_cache_key(target: CanonicalMetricTarget) -> str:
    return f"{target.metric_name}:{target.statement_type}"


def _target_text(target: CanonicalMetricTarget) -> str:
    aliases = ", ".join(_split_identifier(alias) for alias in target.aliases)
    return (
        f"Canonical financial metric: {_split_identifier(target.metric_name)}. "
        f"Financial statement: {target.statement_type}. "
        f"Known SEC XBRL concepts: {aliases}."
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
