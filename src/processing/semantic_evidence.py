"""Versioned semantic evidence packets for unresolved metric targets."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from src.processing.accession_precedence import (
    CompanyPrecedenceResult,
    ConceptIdentity,
    PrecedenceSelectedObservation,
)
from src.processing.arelle_evidence import (
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleFilingResult,
    ArelleFormulaAssertionRecord,
    ArelleRelationshipRecord,
)
from src.processing.mapping_targets import CanonicalMetricTarget

SEMANTIC_EVIDENCE_SCHEMA_VERSION = "1"
_JUDGE_RELATIONSHIP_KINDS = {
    "presentation",
    "calculation",
    "definition",
    "formula",
}


@dataclass(frozen=True)
class SemanticTargetDefinition:
    """One unresolved system metric and its governed concept candidates."""

    metric_name: str
    statement_type: str
    aliases: tuple[str, ...]
    candidate_concepts: tuple[str, ...]
    industry_labels: tuple[str, ...]
    required_for_core: bool
    required_for_specialized_indicators: bool


@dataclass(frozen=True)
class SemanticConceptEvidence:
    """Nonnumeric concept metadata visible to the recommendation judges."""

    evidence_id: str
    taxonomy: str
    concept: str
    label: str | None
    label_source_system: str | None
    documentation: str | None
    documentation_source_system: str | None
    namespace_uri: str | None
    type_qname: str | None
    base_type: str | None
    period_type: str | None
    balance: str | None
    is_numeric: bool | None
    is_abstract: bool | None
    references: tuple[str, ...]
    source_systems: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    component_eligible: bool


@dataclass(frozen=True)
class SemanticRelationshipEvidence:
    """One precedence-selected Arelle relationship without filing lineage."""

    evidence_id: str
    network_kind: str
    arcrole: str
    link_role: str | None
    from_id: str
    to_id: str
    order: str | None
    weight: str | None
    preferred_label: str | None
    target_role: str | None
    usable: bool


@dataclass(frozen=True)
class SemanticFormulaAssertionEvidence:
    """One formula assertion summarized without result counts."""

    assertion_id: str
    assertion_type: str
    status: str


@dataclass(frozen=True)
class SemanticValidationEvidence:
    """One Arelle validation outcome linked to semantic evidence identifiers."""

    evidence_id: str
    severity: str
    code: str
    affected_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class SemanticEvidencePacket:
    """Canonical nonnumeric evidence shared by one exact missing-target set."""

    schema_version: str
    arelle_evidence_status: str
    targets: tuple[SemanticTargetDefinition, ...]
    concepts: tuple[SemanticConceptEvidence, ...]
    relationships: tuple[SemanticRelationshipEvidence, ...]
    formula_assertions: tuple[SemanticFormulaAssertionEvidence, ...]
    validations: tuple[SemanticValidationEvidence, ...]
    content_sha256: str

    def to_json(self) -> str:
        """Return a canonical serialization suitable for audit or comparison."""
        return _canonical_json(asdict(self))


@dataclass(frozen=True)
class SemanticEvidencePeriod:
    """One period's packet and judge lineup before reusable grouping."""

    company_id: str
    period_id: str
    packet: SemanticEvidencePacket
    judge_models: tuple[str, ...]


@dataclass(frozen=True)
class SemanticRecommendationGroup:
    """Periods that can share one recommendation request."""

    recommendation_request_id: str
    company_id: str
    period_ids: tuple[str, ...]
    judge_models: tuple[str, str, str]
    packet: SemanticEvidencePacket


def build_semantic_evidence_packet(
    *,
    precedence: CompanyPrecedenceResult,
    fiscal_year: int,
    fiscal_period: str,
    missing_targets: Sequence[CanonicalMetricTarget],
    arelle_results: Sequence[ArelleFilingResult] = (),
) -> SemanticEvidencePacket:
    """Build the LLM-visible semantic packet for one precedence-selected period."""
    selected = tuple(
        observation
        for observation in precedence.selected_observations
        if observation.observation.fact.fiscal_year == fiscal_year
        and observation.observation.fact.fiscal_period == fiscal_period
    )
    relevant_accessions = {
        observation.accession_number for observation in selected
    }
    relevant_accessions.update(
        network.source_accession_number for network in precedence.statement_networks
    )
    relevant_accessions.update(
        field.source_accession_number
        for resolution in precedence.concept_metadata
        for field in resolution.fields
    )
    relevant_results = tuple(
        sorted(
            (
                result
                for result in arelle_results
                if result.filing.accession_number in relevant_accessions
            ),
            key=lambda item: (
                item.filing.filing_date,
                item.filing.accession_number,
            ),
        )
    )
    concept_records = _concept_records_by_identity(relevant_results)
    fact_concept_ids = _fact_concept_ids(relevant_results)
    eligible_identities = {
        ConceptIdentity(
            taxonomy=observation.observation.fact.taxonomy.casefold(),
            concept=observation.observation.fact.concept,
        )
        for observation in selected
        if observation.observation.fact.value is not None
        and observation.observation.fact.is_numeric is not False
    }
    target_identities = {
        ConceptIdentity(
            taxonomy=candidate.taxonomy.casefold(),
            concept=candidate.concept,
        )
        for target in missing_targets
        for candidate in target.candidate_concepts
    }
    relationship_records: dict[
        str,
        tuple[ArelleRelationshipRecord, bool],
    ] = {}
    for network in precedence.statement_networks:
        for relationship in network.relationships:
            if relationship.network_kind not in _JUDGE_RELATIONSHIP_KINDS:
                continue
            relationship_records[relationship.evidence_id] = (
                relationship,
                True,
            )
        for relationship in network.blocked_relationships:
            if relationship.network_kind not in _JUDGE_RELATIONSHIP_KINDS:
                continue
            relationship_records[relationship.evidence_id] = (
                relationship,
                False,
            )
    seed_evidence_ids = {
        record.evidence_id
        for identity in target_identities
        for record in concept_records.get(identity, ())
    }
    relationship_records = _focused_relationship_records(
        relationship_records,
        seed_evidence_ids=seed_evidence_ids,
        concept_ids_are_available=bool(concept_records),
    )
    identity_by_source_evidence_id = {
        record.evidence_id: identity
        for identity, records in concept_records.items()
        for record in records
    }
    context_identities = {
        identity_by_source_evidence_id[evidence_id]
        for relationship, _usable in relationship_records.values()
        for evidence_id in (relationship.from_id, relationship.to_id)
        if evidence_id in identity_by_source_evidence_id
    }
    available_identities = (
        {resolution.identity for resolution in precedence.concept_metadata}
        | set(concept_records)
        | eligible_identities
    )
    included_identities = (
        eligible_identities
        | context_identities
        | (target_identities & available_identities)
    )
    concepts = _build_concept_evidence(
        precedence=precedence,
        selected=selected,
        eligible_identities=eligible_identities,
        included_identities=included_identities,
        concept_records=concept_records,
    )
    relationships = tuple(
        _relationship_evidence(relationship, usable=usable)
        for relationship, usable in sorted(
            relationship_records.values(),
            key=lambda item: item[0].evidence_id,
        )
    )
    assertions = tuple(
        _formula_assertion_evidence(assertion)
        for assertion in sorted(
            {
                (assertion.assertion_id, assertion.assertion_type): assertion
                for result in relevant_results
                for assertion in result.formula_assertions
            }.values(),
            key=lambda item: (item.assertion_id, item.assertion_type),
        )
    )
    validations = _validation_evidence(
        tuple(
            diagnostic
            for result in relevant_results
            for diagnostic in result.diagnostics
        )
        + tuple(
            diagnostic
            for network in precedence.statement_networks
            for diagnostic in network.blocking_diagnostics
        ),
        fact_concept_ids=fact_concept_ids,
        permitted_evidence_ids={
            relationship.evidence_id for relationship in relationships
        }
        | {
            evidence_id
            for concept in concepts
            for evidence_id in concept.source_evidence_ids
        },
    )
    packet = SemanticEvidencePacket(
        schema_version=SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        arelle_evidence_status=(
            "available" if concept_records else "unavailable"
        ),
        targets=tuple(
            _target_definition(target)
            for target in sorted(
                {
                    (target.metric_name, target.statement_type): target
                    for target in missing_targets
                }.values(),
                key=lambda item: (item.metric_name, item.statement_type),
            )
        ),
        concepts=concepts,
        relationships=relationships,
        formula_assertions=assertions,
        validations=validations,
        content_sha256="",
    )
    return replace(packet, content_sha256=_packet_content_sha256(packet))


def group_semantic_evidence_packets(
    periods: Sequence[SemanticEvidencePeriod],
) -> tuple[SemanticRecommendationGroup, ...]:
    """Group periods only when company, semantic packet, and judges match."""
    grouped: dict[
        tuple[str, str, tuple[str, str, str]],
        list[SemanticEvidencePeriod],
    ] = {}
    seen_periods: set[tuple[str, str]] = set()
    for period in periods:
        company_id = period.company_id.strip()
        period_id = period.period_id.strip()
        if not company_id or not period_id:
            raise ValueError("company_id and period_id must be non-empty")
        judges = _normalize_judge_models(period.judge_models)
        expected_hash = _packet_content_sha256(period.packet)
        if period.packet.content_sha256 != expected_hash:
            raise ValueError("semantic evidence packet content hash did not match")
        period_key = (company_id, period_id)
        if period_key in seen_periods:
            raise ValueError(
                f"duplicate semantic evidence period: {company_id}/{period_id}"
            )
        seen_periods.add(period_key)
        grouped.setdefault(
            (company_id, expected_hash, judges),
            [],
        ).append(period)

    groups: list[SemanticRecommendationGroup] = []
    for (company_id, packet_hash, judges), members in grouped.items():
        request_payload = _canonical_json(
            {
                "company_id": company_id,
                "packet_content_sha256": packet_hash,
                "judge_models": judges,
            }
        )
        groups.append(
            SemanticRecommendationGroup(
                recommendation_request_id=(
                    "semantic-recommendation:"
                    f"{sha256(request_payload.encode('utf-8')).hexdigest()}"
                ),
                company_id=company_id,
                period_ids=tuple(
                    sorted(member.period_id.strip() for member in members)
                ),
                judge_models=judges,
                packet=members[0].packet,
            )
        )
    return tuple(
        sorted(
            groups,
            key=lambda item: (
                item.company_id,
                item.recommendation_request_id,
            ),
        )
    )


def _target_definition(target: CanonicalMetricTarget) -> SemanticTargetDefinition:
    return SemanticTargetDefinition(
        metric_name=target.metric_name,
        statement_type=target.statement_type,
        aliases=tuple(sorted(set(target.aliases))),
        candidate_concepts=tuple(
            sorted(
                {
                    f"{candidate.taxonomy.casefold()}:{candidate.concept}"
                    for candidate in target.candidate_concepts
                }
            )
        ),
        industry_labels=tuple(sorted(set(target.industry_labels))),
        required_for_core=target.required_for_core,
        required_for_specialized_indicators=(
            target.required_for_specialized_indicators
        ),
    )


def _concept_records_by_identity(
    results: Sequence[ArelleFilingResult],
) -> dict[ConceptIdentity, tuple[ArelleConceptRecord, ...]]:
    grouped: dict[ConceptIdentity, dict[str, ArelleConceptRecord]] = {}
    for result in sorted(
        results,
        key=lambda item: (
            item.filing.filing_date,
            item.filing.accession_number,
        ),
    ):
        for concept in result.concepts:
            identity = ConceptIdentity(
                taxonomy=(concept.prefix or concept.namespace_uri).casefold(),
                concept=concept.local_name,
            )
            grouped.setdefault(identity, {})[concept.evidence_id] = concept
    return {
        identity: tuple(
            sorted(records.values(), key=lambda item: item.evidence_id)
        )
        for identity, records in grouped.items()
    }


def _fact_concept_ids(
    results: Sequence[ArelleFilingResult],
) -> dict[str, str]:
    return {
        fact.evidence_id: fact.concept_id
        for result in results
        for fact in result.facts
    }


def _build_concept_evidence(
    *,
    precedence: CompanyPrecedenceResult,
    selected: Sequence[PrecedenceSelectedObservation],
    eligible_identities: set[ConceptIdentity],
    included_identities: set[ConceptIdentity],
    concept_records: dict[ConceptIdentity, tuple[ArelleConceptRecord, ...]],
) -> tuple[SemanticConceptEvidence, ...]:
    metadata_by_identity = {
        resolution.identity: {
            field.name: field for field in resolution.fields
        }
        for resolution in precedence.concept_metadata
    }
    source_systems_by_identity: dict[ConceptIdentity, set[str]] = {}
    for resolution in precedence.concept_metadata:
        source_systems_by_identity[resolution.identity] = {
            field.source_system for field in resolution.fields
        }
    for observation in selected:
        fact = observation.observation.fact
        identity = ConceptIdentity(
            taxonomy=fact.taxonomy.casefold(),
            concept=fact.concept,
        )
        source_systems_by_identity.setdefault(identity, set()).add(fact.source)

    evidence: list[SemanticConceptEvidence] = []
    for identity in included_identities:
        fields = metadata_by_identity.get(identity, {})
        records = concept_records.get(identity, ())
        latest_record = records[-1] if records else None
        label_field = fields.get("label")
        description_field = fields.get("description")
        values = {
            name: field.value
            for name, field in fields.items()
        }
        record = SemanticConceptEvidence(
            evidence_id=_semantic_concept_id(identity),
            taxonomy=identity.taxonomy,
            concept=identity.concept,
            label=_text_value(values.get("label"))
            or (latest_record.label if latest_record else None),
            label_source_system=(
                label_field.source_system
                if label_field is not None
                else (
                    "arelle_structural"
                    if latest_record is not None and latest_record.label
                    else None
                )
            ),
            documentation=_text_value(values.get("description"))
            or (latest_record.documentation if latest_record else None),
            documentation_source_system=(
                description_field.source_system
                if description_field is not None
                else (
                    "arelle_structural"
                    if latest_record is not None and latest_record.documentation
                    else None
                )
            ),
            namespace_uri=_text_value(values.get("namespace_uri"))
            or (latest_record.namespace_uri if latest_record else None),
            type_qname=_text_value(values.get("type_qname"))
            or (latest_record.type_qname if latest_record else None),
            base_type=_text_value(values.get("base_type"))
            or (latest_record.base_type if latest_record else None),
            period_type=_text_value(values.get("period_type"))
            or (latest_record.period_type if latest_record else None),
            balance=_text_value(values.get("balance"))
            or (latest_record.balance if latest_record else None),
            is_numeric=_bool_value(
                values.get("is_numeric"),
                latest_record.is_numeric if latest_record else None,
            ),
            is_abstract=_bool_value(
                values.get("is_abstract"),
                latest_record.is_abstract if latest_record else None,
            ),
            references=_tuple_value(values.get("references"))
            or (latest_record.references if latest_record else ()),
            source_systems=tuple(
                sorted(source_systems_by_identity.get(identity, set()))
            ),
            source_evidence_ids=tuple(
                record.evidence_id for record in records
            ),
            component_eligible=identity in eligible_identities,
        )
        evidence.append(record)
    return tuple(
        sorted(
            evidence,
            key=lambda item: (
                not _is_priority_taxonomy(item.taxonomy),
                item.taxonomy,
                item.concept,
            ),
        )
    )


def _relationship_evidence(
    relationship: ArelleRelationshipRecord,
    *,
    usable: bool,
) -> SemanticRelationshipEvidence:
    return SemanticRelationshipEvidence(
        evidence_id=relationship.evidence_id,
        network_kind=relationship.network_kind,
        arcrole=relationship.arcrole,
        link_role=relationship.link_role,
        from_id=relationship.from_id,
        to_id=relationship.to_id,
        order=relationship.order,
        weight=relationship.weight,
        preferred_label=relationship.preferred_label,
        target_role=relationship.target_role,
        usable=usable,
    )


def _focused_relationship_records(
    records: dict[str, tuple[ArelleRelationshipRecord, bool]],
    *,
    seed_evidence_ids: set[str],
    concept_ids_are_available: bool,
) -> dict[str, tuple[ArelleRelationshipRecord, bool]]:
    if not records:
        return {}
    if not concept_ids_are_available:
        return {}

    networks: dict[
        tuple[str, str, str | None],
        dict[str, tuple[ArelleRelationshipRecord, bool]],
    ] = {}
    for evidence_id, value in records.items():
        relationship = value[0]
        key = (
            relationship.network_kind,
            relationship.arcrole,
            relationship.link_role,
        )
        networks.setdefault(key, {})[evidence_id] = value

    focused: dict[str, tuple[ArelleRelationshipRecord, bool]] = {}
    for network in networks.values():
        adjacency: dict[str, set[str]] = {}
        for relationship, _usable in network.values():
            adjacency.setdefault(relationship.from_id, set()).add(
                relationship.to_id
            )
            adjacency.setdefault(relationship.to_id, set()).add(
                relationship.from_id
            )
        pending = list(seed_evidence_ids & set(adjacency))
        reachable = set(pending)
        while pending:
            current = pending.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    pending.append(neighbor)
        focused.update(
            {
                evidence_id: value
                for evidence_id, value in network.items()
                if value[0].from_id in reachable
                and value[0].to_id in reachable
            }
        )
    return focused


def _formula_assertion_evidence(
    assertion: ArelleFormulaAssertionRecord,
) -> SemanticFormulaAssertionEvidence:
    if assertion.error_message_count:
        status = "error"
    elif assertion.unsatisfied_count:
        status = "unsatisfied"
    elif assertion.warning_message_count:
        status = "warning"
    elif assertion.satisfied_count or assertion.ok_message_count:
        status = "satisfied"
    else:
        status = "not_evaluated"
    return SemanticFormulaAssertionEvidence(
        assertion_id=assertion.assertion_id,
        assertion_type=assertion.assertion_type,
        status=status,
    )


def _validation_evidence(
    diagnostics: Sequence[ArelleDiagnosticRecord],
    *,
    fact_concept_ids: dict[str, str],
    permitted_evidence_ids: set[str],
) -> tuple[SemanticValidationEvidence, ...]:
    validations: dict[
        tuple[str, str, tuple[str, ...]],
        SemanticValidationEvidence,
    ] = {}
    for diagnostic in diagnostics:
        affected = tuple(
            sorted(
                {
                    *(
                        fact_concept_ids[fact_id]
                        for fact_id in diagnostic.fact_ids
                        if fact_id in fact_concept_ids
                    ),
                    *diagnostic.relationship_ids,
                }
            )
        )
        if affected and not permitted_evidence_ids.intersection(affected):
            continue
        key = (diagnostic.severity, diagnostic.code, affected)
        validations[key] = SemanticValidationEvidence(
            evidence_id=_validation_id(diagnostic, affected),
            severity=diagnostic.severity,
            code=diagnostic.code,
            affected_evidence_ids=affected,
        )
    return tuple(
        validations[key]
        for key in sorted(validations)
    )


def _semantic_concept_id(identity: ConceptIdentity) -> str:
    value = f"{identity.taxonomy}:{identity.concept}"
    return f"semantic-concept:{sha256(value.encode('utf-8')).hexdigest()}"


def _validation_id(
    diagnostic: ArelleDiagnosticRecord,
    affected: tuple[str, ...],
) -> str:
    payload = _canonical_json(
        {
            "severity": diagnostic.severity,
            "code": diagnostic.code,
            "affected_evidence_ids": affected,
        }
    )
    return f"validation:{sha256(payload.encode('utf-8')).hexdigest()}"


def _packet_content_sha256(packet: SemanticEvidencePacket) -> str:
    payload = asdict(packet)
    payload.pop("content_sha256")
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _normalize_judge_models(
    models: Sequence[str],
) -> tuple[str, str, str]:
    normalized = tuple(sorted({model.strip() for model in models if model.strip()}))
    if len(models) != 3 or len(normalized) != 3:
        raise ValueError("exactly three distinct judge models are required")
    return normalized


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _text_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _tuple_value(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return ()


def _bool_value(value: object, fallback: bool | None) -> bool | None:
    return value if isinstance(value, bool) else fallback


def _is_priority_taxonomy(taxonomy: str) -> bool:
    return taxonomy.casefold() in {"us-gaap", "sec"}
