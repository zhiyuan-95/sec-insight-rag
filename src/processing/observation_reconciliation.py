"""Same-accession reconciliation for Arelle and Company Facts observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from src.processing.arelle_evidence import (
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleFilingResult,
)
from src.processing.quality import (
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    INCONSISTENT_PERIOD,
    INVALID_DATE,
    MISSING_ACCESSION_NUMBER,
    MISSING_END_DATE,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
)
from src.processing.xbrl_normalizer import NormalizedFact

ARELLE_OBSERVATION_SOURCE = "sec_inline_xbrl"
COMPANY_FACTS_OBSERVATION_SOURCE = "sec_companyfacts"
RECONCILIATION_ARELLE_ONLY = "arelle_only"
RECONCILIATION_AMBIGUOUS_COMPANY_FACTS = "ambiguous_company_facts"
RECONCILIATION_COMPANY_FACTS_ONLY = "company_facts_only"
RECONCILIATION_COMPANY_FACTS_REPLACEMENT = "company_facts_replacement"
RECONCILIATION_MATCHED = "matched"
RECONCILIATION_CONFLICTING = "conflicting"
_UNUSABLE_QUALITY_FLAGS = {
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    INCONSISTENT_PERIOD,
    INVALID_DATE,
    MISSING_ACCESSION_NUMBER,
    MISSING_END_DATE,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
}


@dataclass(frozen=True)
class ReconciliationSourceObservation:
    """One persisted source observation supplied to reconciliation."""

    raw_fact_id: int
    fact: NormalizedFact
    arelle_fact_id: str | None = None


@dataclass(frozen=True)
class ReconciledMetadataField:
    """One retained semantic metadata value and its source."""

    name: str
    value: str | bool
    source: str


@dataclass(frozen=True)
class SemanticFactIdentity:
    """Cross-source identity used by reconciliation and later precedence."""

    cik: str
    taxonomy: str
    concept: str
    start_date: date | None
    end_date: date | None
    unit: str
    dimensions: tuple[tuple[str, str], ...]
    is_consolidated: bool


@dataclass(frozen=True)
class ReconciledObservation:
    """One same-accession reconciliation decision."""

    semantic_identity: SemanticFactIdentity
    outcome: str
    match_kind: str | None
    selected: ReconciliationSourceObservation | None
    source_observations: tuple[ReconciliationSourceObservation, ...]
    availability_markers: tuple[str, ...] = ()
    blocking_diagnostics: tuple[ArelleDiagnosticRecord, ...] = ()
    metadata: tuple[ReconciledMetadataField, ...] = ()


@dataclass(frozen=True)
class AccessionReconciliationResult:
    """Ordered reconciliation decisions for one accession."""

    observations: tuple[ReconciledObservation, ...]
    arelle_result: ArelleFilingResult


def reconcile_accession_observations(
    arelle_result: ArelleFilingResult,
    observations: Sequence[ReconciliationSourceObservation],
) -> AccessionReconciliationResult:
    """Reconcile separately stored observations for one selected accession."""
    _validate_observations(arelle_result, observations)
    grouped: dict[SemanticFactIdentity, list[ReconciliationSourceObservation]] = {}
    for observation in observations:
        grouped.setdefault(_semantic_identity(observation.fact), []).append(
            observation
        )

    reconciled: list[ReconciledObservation] = []
    for semantic_identity, group in grouped.items():
        arelle_observations = tuple(
            item
            for item in group
            if item.fact.source == ARELLE_OBSERVATION_SOURCE
        )
        company_facts_observations = tuple(
            item
            for item in group
            if item.fact.source == COMPANY_FACTS_OBSERVATION_SOURCE
        )
        metadata = _reconcile_metadata(
            arelle_result,
            arelle_observations,
            company_facts_observations,
        )
        company_facts_ambiguous = _company_facts_are_ambiguous(
            company_facts_observations
        )
        if not arelle_observations or not company_facts_observations:
            source_only = (
                arelle_observations or company_facts_observations
            )[0]
            company_facts_ambiguous = (
                not arelle_observations and company_facts_ambiguous
            )
            blocking_diagnostics = (
                _blocking_diagnostics(arelle_result, source_only)
                if arelle_observations
                else ()
            )
            source_only_usable = (
                _numeric_observation_is_usable(source_only)
                and not blocking_diagnostics
            )
            availability_markers: list[str] = []
            if blocking_diagnostics:
                availability_markers.append("arelle_fact_blocked")
            elif not arelle_observations or not source_only_usable:
                availability_markers.append("arelle_fact_unavailable")
            if company_facts_ambiguous:
                availability_markers.append("company_facts_ambiguous")
            elif not arelle_observations and not source_only_usable:
                availability_markers.append("company_facts_unusable")
            reconciled.append(
                ReconciledObservation(
                    semantic_identity=semantic_identity,
                    outcome=(
                        RECONCILIATION_AMBIGUOUS_COMPANY_FACTS
                        if company_facts_ambiguous
                        else (
                            RECONCILIATION_ARELLE_ONLY
                            if arelle_observations
                            else RECONCILIATION_COMPANY_FACTS_ONLY
                        )
                    ),
                    match_kind=None,
                    selected=(
                        source_only
                        if source_only_usable and not company_facts_ambiguous
                        else None
                    ),
                    source_observations=tuple(group),
                    availability_markers=tuple(availability_markers),
                    blocking_diagnostics=blocking_diagnostics,
                    metadata=metadata,
                )
            )
            continue
        arelle = arelle_observations[0]
        company_facts = company_facts_observations[0]
        blocking_diagnostics = _blocking_diagnostics(arelle_result, arelle)
        if company_facts_ambiguous and (
            blocking_diagnostics or not _numeric_observation_is_usable(arelle)
        ):
            reconciled.append(
                ReconciledObservation(
                    semantic_identity=semantic_identity,
                    outcome=RECONCILIATION_AMBIGUOUS_COMPANY_FACTS,
                    match_kind=None,
                    selected=None,
                    source_observations=(arelle, *company_facts_observations),
                    availability_markers=(
                        "arelle_fact_blocked"
                        if blocking_diagnostics
                        else "arelle_fact_unavailable",
                        "company_facts_ambiguous",
                    ),
                    blocking_diagnostics=blocking_diagnostics,
                    metadata=metadata,
                )
            )
            continue
        if blocking_diagnostics or not _numeric_observation_is_usable(arelle):
            company_facts_usable = _numeric_observation_is_usable(company_facts)
            availability_markers = [
                (
                    "arelle_fact_blocked"
                    if blocking_diagnostics
                    else "arelle_fact_unavailable"
                )
            ]
            if not company_facts_usable:
                availability_markers.append("company_facts_unusable")
            reconciled.append(
                ReconciledObservation(
                    semantic_identity=semantic_identity,
                    outcome=RECONCILIATION_COMPANY_FACTS_REPLACEMENT,
                    match_kind=None,
                    selected=company_facts if company_facts_usable else None,
                    source_observations=(arelle, company_facts),
                    availability_markers=tuple(availability_markers),
                    blocking_diagnostics=blocking_diagnostics,
                    metadata=metadata,
                )
            )
            continue
        if company_facts_ambiguous:
            reconciled.append(
                ReconciledObservation(
                    semantic_identity=semantic_identity,
                    outcome=RECONCILIATION_AMBIGUOUS_COMPANY_FACTS,
                    match_kind=None,
                    selected=arelle,
                    source_observations=(arelle, *company_facts_observations),
                    availability_markers=("company_facts_ambiguous",),
                    metadata=metadata,
                )
            )
            continue
        exact_match = arelle.fact.value_raw == company_facts.fact.value_raw
        numeric_match = (
            arelle.fact.value is not None
            and arelle.fact.value == company_facts.fact.value
        )
        reconciled.append(
            ReconciledObservation(
                semantic_identity=semantic_identity,
                outcome=(
                    RECONCILIATION_MATCHED
                    if exact_match or numeric_match
                    else RECONCILIATION_CONFLICTING
                ),
                match_kind=(
                    "exact"
                    if exact_match
                    else "numeric_equivalent" if numeric_match else None
                ),
                selected=arelle,
                source_observations=(arelle, company_facts),
                metadata=metadata,
            )
        )
    return AccessionReconciliationResult(
        observations=tuple(reconciled),
        arelle_result=arelle_result,
    )


def _validate_observations(
    arelle_result: ArelleFilingResult,
    observations: Sequence[ReconciliationSourceObservation],
) -> None:
    for observation in observations:
        if (
            observation.fact.cik != arelle_result.filing.cik
            or observation.fact.accession_number
            != arelle_result.filing.accession_number
        ):
            raise ValueError(
                "Reconciliation observations must belong to one selected accession"
            )
        if observation.fact.source not in {
            ARELLE_OBSERVATION_SOURCE,
            COMPANY_FACTS_OBSERVATION_SOURCE,
        }:
            raise ValueError(
                f"Unsupported reconciliation source: {observation.fact.source}"
            )


def _semantic_identity(fact: NormalizedFact) -> SemanticFactIdentity:
    return SemanticFactIdentity(
        cik=fact.cik,
        taxonomy=fact.taxonomy.casefold(),
        concept=fact.concept,
        start_date=fact.start_date,
        end_date=fact.end_date,
        unit=fact.unit.strip().upper(),
        dimensions=tuple(sorted(fact.dimensions)),
        is_consolidated=fact.is_consolidated,
    )


def _company_facts_are_ambiguous(
    observations: Sequence[ReconciliationSourceObservation],
) -> bool:
    if any(
        {AMBIGUOUS_UNIT, DUPLICATE_FACT} & set(item.fact.quality_flags)
        for item in observations
    ):
        return True
    return len({item.fact.value for item in observations}) > 1


def _numeric_observation_is_usable(
    observation: ReconciliationSourceObservation,
) -> bool:
    fact = observation.fact
    return bool(
        fact.value is not None
        and fact.end_date is not None
        and fact.unit.strip()
        and fact.form in {"10-K", "10-K/A"}
        and fact.is_numeric is not False
        and not (_UNUSABLE_QUALITY_FLAGS & set(fact.quality_flags))
    )


def _reconcile_metadata(
    arelle_result: ArelleFilingResult,
    arelle_observations: Sequence[ReconciliationSourceObservation],
    company_facts_observations: Sequence[ReconciliationSourceObservation],
) -> tuple[ReconciledMetadataField, ...]:
    fields: list[ReconciledMetadataField] = []
    representative = (arelle_observations or company_facts_observations)[0]
    structural_concept = _matching_arelle_concept(
        arelle_result,
        representative.fact,
    )
    for name in ("label", "description", "namespace_uri", "balance", "is_numeric"):
        candidates: list[tuple[str | bool | None, str]] = [
            (getattr(observation.fact, name), observation.fact.source)
            for observation in arelle_observations
        ]
        if structural_concept is not None:
            candidates.append(
                (_structural_metadata_value(structural_concept, name), "arelle_structural")
            )
        candidates.extend(
            (getattr(observation.fact, name), observation.fact.source)
            for observation in company_facts_observations
        )
        for value, source in candidates:
            if value is None or value == "":
                continue
            fields.append(
                ReconciledMetadataField(
                    name=name,
                    value=value,
                    source=source,
                )
            )
            break
    return tuple(fields)


def _matching_arelle_concept(
    arelle_result: ArelleFilingResult,
    fact: NormalizedFact,
) -> ArelleConceptRecord | None:
    for concept in arelle_result.concepts:
        taxonomy_matches = (
            concept.prefix is not None
            and concept.prefix.casefold() == fact.taxonomy.casefold()
        )
        namespace_matches = (
            fact.namespace_uri is not None
            and concept.namespace_uri == fact.namespace_uri
        )
        if concept.local_name == fact.concept and (
            taxonomy_matches or namespace_matches
        ):
            return concept
    return None


def _structural_metadata_value(
    concept: ArelleConceptRecord,
    name: str,
) -> str | bool | None:
    if name == "description":
        return concept.documentation
    return getattr(concept, name)


def _blocking_diagnostics(
    arelle_result: ArelleFilingResult,
    observation: ReconciliationSourceObservation,
) -> tuple[ArelleDiagnosticRecord, ...]:
    if observation.arelle_fact_id is None:
        return ()
    return tuple(
        diagnostic
        for diagnostic in arelle_result.diagnostics
        if diagnostic.severity.casefold() in {"error", "critical", "fatal"}
        and observation.arelle_fact_id in diagnostic.fact_ids
    )
