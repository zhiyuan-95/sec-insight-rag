"""Cross-accession precedence over reconciled annual observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from src.processing.arelle_evidence import (
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleRelationshipRecord,
)
from src.processing.observation_reconciliation import (
    AccessionReconciliationResult,
    ReconciledObservation,
    ReconciliationSourceObservation,
    SemanticFactIdentity,
)
from src.processing.quality import DUPLICATE_FACT


@dataclass(frozen=True)
class PrecedenceObservationCandidate:
    """One accession-scoped reconciliation considered for a fact identity."""

    accession_number: str
    filing_date: date
    reconciliation: ReconciledObservation


@dataclass(frozen=True)
class PrecedenceSelectedObservation:
    """The latest usable observation selected for one semantic identity."""

    semantic_identity: SemanticFactIdentity
    accession_number: str
    filing_date: date
    observation: ReconciliationSourceObservation
    reconciliation: ReconciledObservation


@dataclass(frozen=True)
class FactPrecedenceResolution:
    """Fact-specific accession history and its latest usable selection."""

    semantic_identity: SemanticFactIdentity
    selected: PrecedenceSelectedObservation | None
    candidates: tuple[PrecedenceObservationCandidate, ...]
    invalid_candidates: tuple[PrecedenceObservationCandidate, ...]
    quarantined_candidates: tuple[PrecedenceObservationCandidate, ...]
    equivalent_candidates: tuple[PrecedenceObservationCandidate, ...]


@dataclass(frozen=True)
class StatementNetworkIdentity:
    """The available project identity for one XBRL relationship network."""

    network_kind: str
    arcrole: str
    link_role: str | None


@dataclass(frozen=True)
class PrecedenceStatementNetwork:
    """The newest provided version of one usable statement network."""

    identity: StatementNetworkIdentity
    source_accession_number: str
    source_filing_date: date
    relationships: tuple[ArelleRelationshipRecord, ...]
    blocked_relationships: tuple[ArelleRelationshipRecord, ...] = ()
    blocking_diagnostics: tuple[ArelleDiagnosticRecord, ...] = ()


@dataclass(frozen=True)
class ConceptIdentity:
    """Stable concept identity used for metadata precedence."""

    taxonomy: str
    concept: str


@dataclass(frozen=True)
class PrecedenceMetadataField:
    """One semantic metadata field with source accession lineage."""

    name: str
    value: str | bool | tuple[str, ...]
    source_system: str
    source_accession_number: str
    source_filing_date: date


@dataclass(frozen=True)
class ConceptMetadataResolution:
    """Field-level latest usable metadata for one concept."""

    identity: ConceptIdentity
    fields: tuple[PrecedenceMetadataField, ...]


@dataclass(frozen=True)
class CompanyPrecedenceResult:
    """Precedence-resolved view over a company's reconciled annual history."""

    fact_resolutions: tuple[FactPrecedenceResolution, ...]
    statement_networks: tuple[PrecedenceStatementNetwork, ...]
    concept_metadata: tuple[ConceptMetadataResolution, ...]

    @property
    def selected_observations(self) -> tuple[PrecedenceSelectedObservation, ...]:
        """Return the usable fact view consumed by downstream mapping."""
        return tuple(
            resolution.selected
            for resolution in self.fact_resolutions
            if resolution.selected is not None
        )


@dataclass(frozen=True)
class AccountingContext:
    """Comparable numeric context shared by formula components."""

    cik: str
    start_date: date | None
    end_date: date | None
    unit: str
    dimensions: tuple[tuple[str, str], ...]
    is_consolidated: bool


def resolve_accession_precedence(
    reconciliations: Sequence[AccessionReconciliationResult],
) -> CompanyPrecedenceResult:
    """Select the latest usable observation for every semantic fact identity."""
    grouped: dict[SemanticFactIdentity, list[PrecedenceObservationCandidate]] = {}
    for reconciliation in reconciliations:
        filing = reconciliation.arelle_result.filing
        filing_date = date.fromisoformat(filing.filing_date)
        for observation in reconciliation.observations:
            grouped.setdefault(observation.semantic_identity, []).append(
                PrecedenceObservationCandidate(
                    accession_number=filing.accession_number,
                    filing_date=filing_date,
                    reconciliation=observation,
                )
            )

    resolutions: list[FactPrecedenceResolution] = []
    for identity, candidates in grouped.items():
        ordered = tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    candidate.filing_date,
                    candidate.accession_number,
                ),
            )
        )
        latest_usable = next(
            (
                candidate
                for candidate in reversed(ordered)
                if candidate.reconciliation.selected is not None
            ),
            None,
        )
        selected = None
        if latest_usable is not None:
            selected_observation = latest_usable.reconciliation.selected
            assert selected_observation is not None
            selected = PrecedenceSelectedObservation(
                semantic_identity=identity,
                accession_number=latest_usable.accession_number,
                filing_date=latest_usable.filing_date,
                observation=selected_observation,
                reconciliation=latest_usable.reconciliation,
            )
        equivalent_candidates = (
            tuple(
                candidate
                for candidate in ordered
                if _candidate_values_are_equivalent(candidate, latest_usable)
            )
            if latest_usable is not None
            else ()
        )
        quarantined_candidates = tuple(
            candidate
            for candidate in ordered
            if _candidate_is_quarantined(candidate)
        )
        resolutions.append(
            FactPrecedenceResolution(
                semantic_identity=identity,
                selected=selected,
                candidates=ordered,
                invalid_candidates=tuple(
                    candidate
                    for candidate in ordered
                    if candidate.reconciliation.selected is None
                    and candidate not in quarantined_candidates
                ),
                quarantined_candidates=quarantined_candidates,
                equivalent_candidates=equivalent_candidates,
            )
        )

    return CompanyPrecedenceResult(
        fact_resolutions=tuple(resolutions),
        statement_networks=_resolve_statement_networks(reconciliations),
        concept_metadata=_resolve_concept_metadata(reconciliations),
    )


def select_compatible_components(
    result: CompanyPrecedenceResult,
    semantic_identities: Sequence[SemanticFactIdentity],
) -> tuple[PrecedenceSelectedObservation, ...]:
    """Return selected components only when their accounting contexts match."""
    resolutions = {
        resolution.semantic_identity: resolution
        for resolution in result.fact_resolutions
    }
    selected: list[PrecedenceSelectedObservation] = []
    expected_context: AccountingContext | None = None
    for identity in semantic_identities:
        resolution = resolutions.get(identity)
        if resolution is None or resolution.selected is None:
            raise ValueError(
                "No precedence-selected observation exists for component "
                f"{identity.taxonomy}:{identity.concept}"
            )
        context = _accounting_context(identity)
        if expected_context is None:
            expected_context = context
        elif context != expected_context:
            raise ValueError("Selected components have incompatible accounting contexts")
        selected.append(resolution.selected)
    return tuple(selected)


def _accounting_context(identity: SemanticFactIdentity) -> AccountingContext:
    return AccountingContext(
        cik=identity.cik,
        start_date=identity.start_date,
        end_date=identity.end_date,
        unit=identity.unit,
        dimensions=identity.dimensions,
        is_consolidated=identity.is_consolidated,
    )


def _resolve_concept_metadata(
    reconciliations: Sequence[AccessionReconciliationResult],
) -> tuple[ConceptMetadataResolution, ...]:
    selected: dict[ConceptIdentity, dict[str, PrecedenceMetadataField]] = {}
    ordered_reconciliations = sorted(
        reconciliations,
        key=lambda item: (
            date.fromisoformat(item.arelle_result.filing.filing_date),
            item.arelle_result.filing.accession_number,
        ),
    )
    for reconciliation in ordered_reconciliations:
        result = reconciliation.arelle_result
        filing_date = date.fromisoformat(result.filing.filing_date)
        for concept in result.concepts:
            identity = ConceptIdentity(
                taxonomy=(concept.prefix or concept.namespace_uri).casefold(),
                concept=concept.local_name,
            )
            fields = selected.setdefault(identity, {})
            for name, value in _concept_metadata_values(concept):
                if value is None or value == "" or value == ():
                    continue
                fields[name] = PrecedenceMetadataField(
                    name=name,
                    value=value,
                    source_system="arelle_structural",
                    source_accession_number=result.filing.accession_number,
                    source_filing_date=filing_date,
                )
        for observation in reconciliation.observations:
            identity = ConceptIdentity(
                taxonomy=observation.semantic_identity.taxonomy,
                concept=observation.semantic_identity.concept,
            )
            fields = selected.setdefault(identity, {})
            for field in observation.metadata:
                fields[field.name] = PrecedenceMetadataField(
                    name=field.name,
                    value=field.value,
                    source_system=field.source,
                    source_accession_number=result.filing.accession_number,
                    source_filing_date=filing_date,
                )
    return tuple(
        ConceptMetadataResolution(
            identity=identity,
            fields=tuple(
                selected[identity][name]
                for name in sorted(selected[identity])
            ),
        )
        for identity in sorted(
            selected,
            key=lambda item: (item.taxonomy, item.concept),
        )
    )


def _concept_metadata_values(
    concept: ArelleConceptRecord,
) -> tuple[tuple[str, str | bool | tuple[str, ...] | None], ...]:
    return (
        ("label", concept.label),
        ("description", concept.documentation),
        ("namespace_uri", concept.namespace_uri),
        ("type_qname", concept.type_qname),
        ("base_type", concept.base_type),
        ("period_type", concept.period_type),
        ("balance", concept.balance),
        ("is_numeric", concept.is_numeric),
        ("is_abstract", concept.is_abstract),
        ("references", concept.references),
    )


def _resolve_statement_networks(
    reconciliations: Sequence[AccessionReconciliationResult],
) -> tuple[PrecedenceStatementNetwork, ...]:
    selected: dict[StatementNetworkIdentity, PrecedenceStatementNetwork] = {}
    ordered_reconciliations = sorted(
        reconciliations,
        key=lambda item: (
            date.fromisoformat(item.arelle_result.filing.filing_date),
            item.arelle_result.filing.accession_number,
        ),
    )
    for reconciliation in ordered_reconciliations:
        result = reconciliation.arelle_result
        grouped: dict[StatementNetworkIdentity, list[ArelleRelationshipRecord]] = {}
        for relationship in result.relationships:
            identity = StatementNetworkIdentity(
                network_kind=relationship.network_kind,
                arcrole=relationship.arcrole,
                link_role=relationship.link_role,
            )
            grouped.setdefault(identity, []).append(relationship)
        for identity, relationships in grouped.items():
            relationship_ids = {
                relationship.evidence_id for relationship in relationships
            }
            blocking_diagnostics = tuple(
                diagnostic
                for diagnostic in result.diagnostics
                if diagnostic.severity.casefold() in {"error", "critical", "fatal"}
                and relationship_ids.intersection(diagnostic.relationship_ids)
            )
            blocked_ids = {
                relationship_id
                for diagnostic in blocking_diagnostics
                for relationship_id in diagnostic.relationship_ids
            }
            usable_relationships = tuple(
                relationship
                for relationship in relationships
                if relationship.evidence_id not in blocked_ids
            )
            if not usable_relationships:
                continue
            selected[identity] = PrecedenceStatementNetwork(
                identity=identity,
                source_accession_number=result.filing.accession_number,
                source_filing_date=date.fromisoformat(result.filing.filing_date),
                relationships=usable_relationships,
                blocked_relationships=tuple(
                    relationship
                    for relationship in relationships
                    if relationship.evidence_id in blocked_ids
                ),
                blocking_diagnostics=blocking_diagnostics,
            )
    return tuple(
        selected[identity]
        for identity in sorted(
            selected,
            key=lambda item: (
                item.network_kind,
                item.arcrole,
                item.link_role or "",
            ),
        )
    )


def _candidate_is_quarantined(candidate: PrecedenceObservationCandidate) -> bool:
    return candidate.reconciliation.selected is None and any(
        DUPLICATE_FACT in observation.fact.quality_flags
        for observation in candidate.reconciliation.source_observations
    )


def _candidate_values_are_equivalent(
    candidate: PrecedenceObservationCandidate,
    selected: PrecedenceObservationCandidate,
) -> bool:
    candidate_observation = candidate.reconciliation.selected
    selected_observation = selected.reconciliation.selected
    if candidate_observation is None or selected_observation is None:
        return False
    candidate_fact = candidate_observation.fact
    selected_fact = selected_observation.fact
    if candidate_fact.value is not None and selected_fact.value is not None:
        return candidate_fact.value == selected_fact.value
    return candidate_fact.value_raw == selected_fact.value_raw
