"""In-memory duplicate and accession precedence for Plan 203 observations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TypeAlias

from src.processing.arelle_records import ArelleFilingResult, ExtractedFact


DUPLICATE_FACT = "duplicate_fact"
DEGRADED_ACCESSION = "degraded_accession"
NIL_FACT = "nil_fact"
MISSING_PRECEDENCE_METADATA = "missing_precedence_metadata"

SemanticFactKey: TypeAlias = tuple[object, ...]


@dataclass(frozen=True)
class ArelleObservation:
    """One deterministic accession observation and its eligibility state."""

    accession_number: str
    form: str | None
    filing_date: str | None
    result_status: str
    fact: ExtractedFact
    occurrence_count: int
    quality_flags: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return not self.quality_flags


@dataclass(frozen=True)
class ArellePrecedenceResult:
    """Selected current observations plus every quarantined observation."""

    selected: tuple[ArelleObservation, ...]
    quarantined: tuple[ArelleObservation, ...]


def apply_arelle_accession_precedence(
    results: list[ArelleFilingResult] | tuple[ArelleFilingResult, ...],
) -> ArellePrecedenceResult:
    """Select complete, non-nil, unambiguous facts within each form family.

    Later accessions replace only the same semantic fact identity. Omission never
    removes an older observation, and annual and quarterly form families remain
    separate.
    """
    accessions = [result.accession_number for result in results]
    if len(accessions) != len(set(accessions)):
        raise ValueError("Arelle precedence requires one result per accession")

    candidates_by_identity: dict[
        tuple[str, SemanticFactKey], list[ArelleObservation]
    ] = defaultdict(list)
    quarantined: list[ArelleObservation] = []

    for result in results:
        occurrence_groups: dict[SemanticFactKey, list[tuple[int, ExtractedFact]]] = (
            defaultdict(list)
        )
        for index, fact in enumerate(result.facts):
            occurrence_groups[_semantic_fact_key(fact)].append((index, fact))

        for semantic_key, occurrences in occurrence_groups.items():
            representative = min(occurrences, key=_occurrence_order)[1]
            flags = _observation_flags(result, len(occurrences), representative)
            observation = ArelleObservation(
                accession_number=result.accession_number,
                form=result.form,
                filing_date=result.filing_date,
                result_status=result.status,
                fact=representative,
                occurrence_count=len(occurrences),
                quality_flags=flags,
            )
            form_family = _form_family(result.form)
            if flags or form_family is None:
                quarantined.append(observation)
                continue
            candidates_by_identity[(form_family, semantic_key)].append(observation)

    selected = [
        max(observations, key=_observation_order)
        for observations in candidates_by_identity.values()
    ]
    return ArellePrecedenceResult(
        selected=tuple(sorted(selected, key=_output_order)),
        quarantined=tuple(sorted(quarantined, key=_output_order)),
    )


def _observation_flags(
    result: ArelleFilingResult,
    occurrence_count: int,
    fact: ExtractedFact,
) -> tuple[str, ...]:
    flags: list[str] = []
    if result.status != "complete":
        flags.append(DEGRADED_ACCESSION)
    if occurrence_count > 1:
        flags.append(DUPLICATE_FACT)
    if fact.nil:
        flags.append(NIL_FACT)
    if _form_family(result.form) is None or not _valid_date(result.filing_date):
        flags.append(MISSING_PRECEDENCE_METADATA)
    return tuple(flags)


def _semantic_fact_key(fact: ExtractedFact) -> SemanticFactKey:
    context = fact.context_key
    return (
        context.entity_scheme,
        context.entity_identifier,
        fact.concept_key,
        context.period_type,
        context.start_date,
        context.end_date,
        context.instant_date,
        fact.unit_key,
        context.dimensions,
    )


def _form_family(form: str | None) -> str | None:
    normalized = form.strip().upper() if form is not None else ""
    if normalized in {"10-K", "10-K/A"}:
        return "10-K"
    if normalized in {"10-Q", "10-Q/A"}:
        return "10-Q"
    return None


def _valid_date(value: str | None) -> bool:
    if value is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _occurrence_order(item: tuple[int, ExtractedFact]) -> tuple[object, ...]:
    index, fact = item
    return (
        fact.source_line if fact.source_line is not None else 2**63,
        fact.source_document or "",
        index,
    )


def _observation_order(observation: ArelleObservation) -> tuple[str, str]:
    return observation.filing_date or "", observation.accession_number


def _output_order(observation: ArelleObservation) -> tuple[object, ...]:
    fact = observation.fact
    return (
        _form_family(observation.form) or "",
        fact.concept_key.namespace_uri,
        fact.concept_key.local_name,
        repr(_semantic_fact_key(fact)),
        observation.filing_date or "",
        observation.accession_number,
    )
