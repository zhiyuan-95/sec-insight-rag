"""Deterministic period application of unanimous semantic recommendations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from src.processing.accession_precedence import (
    CompanyPrecedenceResult,
    PrecedenceSelectedObservation,
)
from src.processing.arelle_evidence import ArelleDiagnosticRecord
from src.processing.company_identity import same_cik
from src.processing.semantic_recommendations import (
    RECOMMENDATION_UNANIMOUS_FORMULA,
    RECOMMENDATION_UNANIMOUS_ZERO,
    SemanticRecommendationRecord,
    SemanticTargetComparison,
)

RECOVERY_APPLICATION_SUCCEEDED = "succeeded"
RECOVERY_APPLICATION_INVALID = "invalid_proposal"


@dataclass(frozen=True)
class AffirmativeZeroEvidence:
    """Arelle-backed deterministic proof that one target is zero."""

    company_id: str
    target_metric_name: str
    statement_type: str
    evidence_id: str
    taxonomy: str
    concept: str
    raw_fact_id: int
    arelle_fact_id: str
    value_numeric: Decimal
    source_accession_number: str
    source_system: str
    fiscal_year: int
    fiscal_period: str
    unit: str
    period_type: str
    start_date: date | None
    end_date: date | None
    filing_date: date
    dimensions: tuple[tuple[str, str], ...]
    is_consolidated: bool


@dataclass(frozen=True)
class RecoveryComponentDiagnostic:
    """Blocking Arelle diagnostic retained with a rejected component."""

    severity: str
    code: str
    message: str
    fact_ids: tuple[str, ...]
    relationship_ids: tuple[str, ...]
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryComponentApplication:
    """One resolved numeric component in a period recovery application."""

    taxonomy: str
    concept: str
    operator: Literal["+", "-"]
    evidence_refs: tuple[str, ...]
    raw_fact_id: int
    accession_number: str
    source_system: str
    value_numeric: Decimal
    unit: str
    period_type: str
    start_date: date | None
    end_date: date | None
    filing_date: date
    blocking_diagnostics: tuple[RecoveryComponentDiagnostic, ...] = ()


@dataclass(frozen=True)
class RecoveryApplication:
    """Period-specific numeric proof for one unanimous target decision."""

    recommendation_request_id: str
    recommendation_attempt_number: int
    company_id: str
    period_id: str
    target_metric_name: str
    statement_type: str
    decision: str
    status: str
    failure_reason: str | None
    fiscal_year: int
    fiscal_period: str
    value_numeric: Decimal | None
    unit: str | None
    period_type: str | None
    start_date: date | None
    end_date: date | None
    filing_date: date | None
    source_raw_fact_ids: tuple[int, ...]
    source_accession_numbers: tuple[str, ...]
    components: tuple[RecoveryComponentApplication, ...]
    zero_evidence: AffirmativeZeroEvidence | None = None


def apply_semantic_recommendation_to_period(
    *,
    recommendation: SemanticRecommendationRecord,
    precedence: CompanyPrecedenceResult,
    period_id: str,
    fiscal_year: int,
    fiscal_period: str,
    expected_start_date: date | None,
    expected_end_date: date,
    affirmative_zero_evidence: tuple[AffirmativeZeroEvidence, ...] = (),
) -> tuple[RecoveryApplication, ...]:
    """Apply every unanimous formula/zero decision independently to one period."""
    clean_period_id = period_id.strip()
    if clean_period_id not in recommendation.period_ids:
        raise ValueError(
            "period_id is not covered by the semantic recommendation"
        )
    packet = json.loads(recommendation.packet_json)
    eligible_concepts = {
        (
            str(concept["taxonomy"]).casefold(),
            str(concept["concept"]),
        )
        for concept in packet.get("concepts", [])
        if concept.get("component_eligible") is True
    }
    applications = []
    for comparison in recommendation.target_comparisons:
        if comparison.outcome == RECOMMENDATION_UNANIMOUS_FORMULA:
            applications.append(
                _apply_formula(
                    recommendation=recommendation,
                    comparison=comparison,
                    precedence=precedence,
                    period_id=clean_period_id,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    expected_start_date=expected_start_date,
                    expected_end_date=expected_end_date,
                    eligible_concepts=eligible_concepts,
                )
            )
        elif comparison.outcome == RECOMMENDATION_UNANIMOUS_ZERO:
            applications.append(
                _apply_zero(
                    recommendation=recommendation,
                    comparison=comparison,
                    packet=packet,
                    period_id=clean_period_id,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    expected_start_date=expected_start_date,
                    expected_end_date=expected_end_date,
                    precedence=precedence,
                    affirmative_zero_evidence=affirmative_zero_evidence,
                )
            )
    return tuple(applications)


def recovery_application_to_json(
    application: RecoveryApplication,
) -> str:
    """Serialize one application canonically for immutable storage."""
    return json.dumps(
        _json_value(asdict(application)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def recovery_application_from_json(value: str) -> RecoveryApplication:
    """Restore one application from its canonical stored representation."""
    payload = json.loads(value)
    components = tuple(
        RecoveryComponentApplication(
            taxonomy=component["taxonomy"],
            concept=component["concept"],
            operator=component["operator"],
            evidence_refs=tuple(component["evidence_refs"]),
            raw_fact_id=component["raw_fact_id"],
            accession_number=component["accession_number"],
            source_system=component["source_system"],
            value_numeric=Decimal(component["value_numeric"]),
            unit=component["unit"],
            period_type=component["period_type"],
            start_date=_date_value(component["start_date"]),
            end_date=_date_value(component["end_date"]),
            filing_date=date.fromisoformat(component["filing_date"]),
            blocking_diagnostics=tuple(
                RecoveryComponentDiagnostic(
                    severity=diagnostic["severity"],
                    code=diagnostic["code"],
                    message=diagnostic["message"],
                    fact_ids=tuple(diagnostic["fact_ids"]),
                    relationship_ids=tuple(
                        diagnostic["relationship_ids"]
                    ),
                    source_references=tuple(
                        diagnostic["source_references"]
                    ),
                )
                for diagnostic in component.get(
                    "blocking_diagnostics",
                    (),
                )
            ),
        )
        for component in payload["components"]
    )
    zero_payload = payload["zero_evidence"]
    zero_evidence = (
        AffirmativeZeroEvidence(
            company_id=zero_payload["company_id"],
            target_metric_name=zero_payload["target_metric_name"],
            statement_type=zero_payload["statement_type"],
            evidence_id=zero_payload["evidence_id"],
            taxonomy=zero_payload["taxonomy"],
            concept=zero_payload["concept"],
            raw_fact_id=zero_payload["raw_fact_id"],
            arelle_fact_id=zero_payload["arelle_fact_id"],
            value_numeric=Decimal(zero_payload["value_numeric"]),
            source_accession_number=zero_payload[
                "source_accession_number"
            ],
            source_system=zero_payload["source_system"],
            fiscal_year=zero_payload["fiscal_year"],
            fiscal_period=zero_payload["fiscal_period"],
            unit=zero_payload["unit"],
            period_type=zero_payload["period_type"],
            start_date=_date_value(zero_payload["start_date"]),
            end_date=_date_value(zero_payload["end_date"]),
            filing_date=date.fromisoformat(zero_payload["filing_date"]),
            dimensions=tuple(
                tuple(item) for item in zero_payload["dimensions"]
            ),
            is_consolidated=zero_payload["is_consolidated"],
        )
        if zero_payload is not None
        else None
    )
    return RecoveryApplication(
        recommendation_request_id=payload["recommendation_request_id"],
        recommendation_attempt_number=payload[
            "recommendation_attempt_number"
        ],
        company_id=payload["company_id"],
        period_id=payload["period_id"],
        target_metric_name=payload["target_metric_name"],
        statement_type=payload["statement_type"],
        decision=payload["decision"],
        status=payload["status"],
        failure_reason=payload["failure_reason"],
        fiscal_year=payload["fiscal_year"],
        fiscal_period=payload["fiscal_period"],
        value_numeric=(
            Decimal(payload["value_numeric"])
            if payload["value_numeric"] is not None
            else None
        ),
        unit=payload["unit"],
        period_type=payload["period_type"],
        start_date=_date_value(payload["start_date"]),
        end_date=_date_value(payload["end_date"]),
        filing_date=_date_value(payload["filing_date"]),
        source_raw_fact_ids=tuple(payload["source_raw_fact_ids"]),
        source_accession_numbers=tuple(
            payload["source_accession_numbers"]
        ),
        components=components,
        zero_evidence=zero_evidence,
    )


def validate_recovery_application(
    application: RecoveryApplication,
    comparison: SemanticTargetComparison,
    packet_json: str,
) -> None:
    """Reject stored applications that do not contain a deterministic proof."""
    if application.status == RECOVERY_APPLICATION_INVALID:
        if application.value_numeric is not None:
            _raise_invalid_proof()
        return
    if (
        application.status != RECOVERY_APPLICATION_SUCCEEDED
        or application.failure_reason is not None
    ):
        _raise_invalid_proof()

    packet = json.loads(packet_json)
    canonical = _canonical_decision(comparison)
    if application.decision == "formula":
        component_specs = canonical.get("components")
        if (
            canonical.get("decision") != "formula"
            or not isinstance(component_specs, list)
            or not component_specs
            or application.zero_evidence is not None
        ):
            _raise_invalid_proof()
        expected_components = tuple(
            (
                str(component.get("taxonomy") or ""),
                str(component.get("concept") or ""),
                component.get("operator"),
                _text_tuple(component.get("evidence_refs")),
            )
            for component in component_specs
            if isinstance(component, dict)
        )
        actual_components = tuple(
            (
                component.taxonomy,
                component.concept,
                component.operator,
                component.evidence_refs,
            )
            for component in application.components
        )
        if (
            len(expected_components) != len(component_specs)
            or expected_components != actual_components
            or any(
                component.blocking_diagnostics
                for component in application.components
            )
            or _component_incompatibility(
                list(application.components),
                statement_type=application.statement_type,
                target_metric_name=application.target_metric_name,
                expected_start_date=application.start_date,
                expected_end_date=application.end_date,
            )
            is not None
        ):
            _raise_invalid_proof()
        calculated = sum(
            (
                component.value_numeric
                if component.operator == "+"
                else -component.value_numeric
            )
            for component in application.components
        )
        first = application.components[0]
        if (
            application.value_numeric != calculated
            or application.unit != first.unit
            or application.period_type != first.period_type
            or application.start_date != first.start_date
            or application.end_date != first.end_date
            or application.filing_date
            != max(
                component.filing_date
                for component in application.components
            )
            or application.source_raw_fact_ids
            != tuple(
                sorted(
                    component.raw_fact_id
                    for component in application.components
                )
            )
            or application.source_accession_numbers
            != tuple(
                sorted(
                    {
                        component.accession_number
                        for component in application.components
                    }
                )
            )
        ):
            _raise_invalid_proof()
        return

    evidence = application.zero_evidence
    cited_evidence = set(_text_tuple(canonical.get("evidence_refs")))
    if (
        application.decision != "zero"
        or canonical.get("decision") != "zero"
        or evidence is None
        or application.components
        or evidence.evidence_id not in cited_evidence
        or not _packet_has_zero_concept(packet, evidence)
        or not evidence.arelle_fact_id
        or evidence.raw_fact_id <= 0
        or evidence.value_numeric != Decimal("0")
        or not evidence.is_consolidated
        or evidence.dimensions
        or not same_cik(evidence.company_id, application.company_id)
        or evidence.target_metric_name != application.target_metric_name
        or evidence.statement_type != application.statement_type
        or _unit_family(evidence.unit)
        != _target_unit_family(
            application.target_metric_name,
            application.statement_type,
        )
        or application.value_numeric != Decimal("0")
        or application.unit != evidence.unit
        or application.period_type != evidence.period_type
        or application.start_date != evidence.start_date
        or application.end_date != evidence.end_date
        or application.filing_date != evidence.filing_date
        or application.fiscal_year != evidence.fiscal_year
        or application.fiscal_period != evidence.fiscal_period
        or application.source_raw_fact_ids != (evidence.raw_fact_id,)
        or application.source_accession_numbers
        != (evidence.source_accession_number,)
    ):
        _raise_invalid_proof()


def _raise_invalid_proof() -> None:
    raise ValueError(
        "recovery application does not contain a valid deterministic "
        "recovery proof"
    )


def recovery_metric_source_accession(
    application: RecoveryApplication,
) -> str:
    """Return the source accession that supplies recovered metric recency."""
    if application.decision == "formula" and application.components:
        source = max(
            application.components,
            key=lambda component: (
                component.filing_date,
                component.accession_number,
            ),
        )
        accession_number = source.accession_number
        filing_date = source.filing_date
    elif application.decision == "zero" and application.zero_evidence:
        accession_number = (
            application.zero_evidence.source_accession_number
        )
        filing_date = application.zero_evidence.filing_date
    else:
        raise ValueError(
            "successful recovery application lacks source lineage"
        )
    if (
        accession_number not in application.source_accession_numbers
        or filing_date != application.filing_date
    ):
        raise ValueError(
            "successful recovery application has inconsistent source lineage"
        )
    return accession_number


def _apply_formula(
    *,
    recommendation: SemanticRecommendationRecord,
    comparison: SemanticTargetComparison,
    precedence: CompanyPrecedenceResult,
    period_id: str,
    fiscal_year: int,
    fiscal_period: str,
    expected_start_date: date | None,
    expected_end_date: date,
    eligible_concepts: set[tuple[str, str]],
) -> RecoveryApplication:
    canonical = _canonical_decision(comparison)
    if canonical.get("decision") != "formula":
        return _invalid_application(
            recommendation=recommendation,
            comparison=comparison,
            period_id=period_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            decision=str(canonical.get("decision") or ""),
            failure_reason="canonical_decision_mismatch",
        )
    component_specs = canonical.get("components")
    if not isinstance(component_specs, list) or not component_specs:
        return _invalid_application(
            recommendation=recommendation,
            comparison=comparison,
            period_id=period_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            decision="formula",
            failure_reason="formula_components_unavailable",
        )

    identities: set[tuple[str, str]] = set()
    resolved: list[RecoveryComponentApplication] = []
    for component_spec in component_specs:
        if not isinstance(component_spec, dict):
            return _invalid_application(
                recommendation=recommendation,
                comparison=comparison,
                period_id=period_id,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                decision="formula",
                failure_reason="malformed_formula_component",
                components=tuple(resolved),
            )
        taxonomy = str(component_spec.get("taxonomy") or "").strip()
        concept = str(component_spec.get("concept") or "").strip()
        operator = component_spec.get("operator")
        identity = (taxonomy.casefold(), concept)
        if (
            not taxonomy
            or not concept
            or operator not in {"+", "-"}
            or identity not in eligible_concepts
            or identity in identities
        ):
            return _invalid_application(
                recommendation=recommendation,
                comparison=comparison,
                period_id=period_id,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                decision="formula",
                failure_reason=f"ineligible_formula_component:{taxonomy}:{concept}",
                components=tuple(resolved),
            )
        identities.add(identity)
        candidates = _component_candidates(
            precedence=precedence,
            company_id=recommendation.company_id,
            taxonomy=taxonomy,
            concept=concept,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
        )
        context_candidates = tuple(
            selected
            for selected in candidates
            if (
                selected.observation.fact.start_date
                == expected_start_date
                and selected.observation.fact.end_date
                == expected_end_date
            )
        )
        if len(context_candidates) == 1:
            selected = context_candidates[0]
        elif len(candidates) == 1:
            selected = candidates[0]
        else:
            reason = (
                "component_fact_unavailable"
                if not context_candidates
                else "component_fact_ambiguous"
            )
            return _invalid_application(
                recommendation=recommendation,
                comparison=comparison,
                period_id=period_id,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                decision="formula",
                failure_reason=f"{reason}:{taxonomy}:{concept}",
                components=tuple(resolved),
            )
        fact = selected.observation.fact
        assert fact.value is not None
        component = RecoveryComponentApplication(
            taxonomy=taxonomy,
            concept=concept,
            operator=operator,
            evidence_refs=_text_tuple(
                component_spec.get("evidence_refs")
            ),
            raw_fact_id=selected.observation.raw_fact_id,
            accession_number=selected.accession_number,
            source_system=fact.source,
            value_numeric=fact.value,
            unit=fact.unit,
            period_type=fact.period_type,
            start_date=fact.start_date,
            end_date=fact.end_date,
            filing_date=selected.filing_date,
            blocking_diagnostics=tuple(
                _component_diagnostic(diagnostic)
                for diagnostic in _blocking_fact_diagnostics(selected)
            ),
        )
        resolved.append(component)
        if component.blocking_diagnostics:
            return _invalid_application(
                recommendation=recommendation,
                comparison=comparison,
                period_id=period_id,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                decision="formula",
                failure_reason=(
                    f"component_blocking_diagnostic:{taxonomy}:{concept}"
                ),
                components=tuple(resolved),
            )

    incompatibility = _component_incompatibility(
        resolved,
        statement_type=comparison.statement_type,
        target_metric_name=comparison.target_metric_name,
        expected_start_date=expected_start_date,
        expected_end_date=expected_end_date,
    )
    if incompatibility is not None:
        return _invalid_application(
            recommendation=recommendation,
            comparison=comparison,
            period_id=period_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            decision="formula",
            failure_reason=incompatibility,
            components=tuple(resolved),
        )

    value = sum(
        (
            component.value_numeric
            if component.operator == "+"
            else -component.value_numeric
        )
        for component in resolved
    )
    first = resolved[0]
    return RecoveryApplication(
        recommendation_request_id=recommendation.recommendation_request_id,
        recommendation_attempt_number=recommendation.attempt_number,
        company_id=recommendation.company_id,
        period_id=period_id,
        target_metric_name=comparison.target_metric_name,
        statement_type=comparison.statement_type,
        decision="formula",
        status=RECOVERY_APPLICATION_SUCCEEDED,
        failure_reason=None,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        value_numeric=value,
        unit=first.unit,
        period_type=first.period_type,
        start_date=first.start_date,
        end_date=first.end_date,
        filing_date=max(component.filing_date for component in resolved),
        source_raw_fact_ids=tuple(
            sorted(component.raw_fact_id for component in resolved)
        ),
        source_accession_numbers=tuple(
            sorted(
                {
                    component.accession_number
                    for component in resolved
                }
            )
        ),
        components=tuple(resolved),
    )


def _apply_zero(
    *,
    recommendation: SemanticRecommendationRecord,
    comparison: SemanticTargetComparison,
    packet: dict[str, Any],
    period_id: str,
    fiscal_year: int,
    fiscal_period: str,
    expected_start_date: date | None,
    expected_end_date: date,
    precedence: CompanyPrecedenceResult,
    affirmative_zero_evidence: tuple[AffirmativeZeroEvidence, ...],
) -> RecoveryApplication:
    canonical = _canonical_decision(comparison)
    if canonical.get("decision") != "zero":
        return _invalid_application(
            recommendation=recommendation,
            comparison=comparison,
            period_id=period_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            decision=str(canonical.get("decision") or ""),
            failure_reason="canonical_decision_mismatch",
        )
    cited_evidence = set(_text_tuple(canonical.get("evidence_refs")))
    matching = tuple(
        evidence
        for evidence in affirmative_zero_evidence
        if (
            same_cik(evidence.company_id, recommendation.company_id)
            and evidence.target_metric_name
            == comparison.target_metric_name
            and evidence.statement_type == comparison.statement_type
            and evidence.fiscal_year == fiscal_year
            and evidence.fiscal_period == fiscal_period
            and evidence.evidence_id in cited_evidence
            and _packet_has_zero_concept(packet, evidence)
            and _zero_evidence_matches_precedence(
                precedence,
                evidence,
            )
            and evidence.value_numeric == Decimal("0")
            and evidence.is_consolidated
            and not evidence.dimensions
            and evidence.start_date == expected_start_date
            and evidence.end_date == expected_end_date
            and _unit_family(evidence.unit)
            == _target_unit_family(
                comparison.target_metric_name,
                comparison.statement_type,
            )
            and _zero_period_type_is_compatible(
                evidence.period_type,
                comparison.statement_type,
            )
        )
    )
    if packet.get("arelle_evidence_status") != "available" or not matching:
        return _invalid_application(
            recommendation=recommendation,
            comparison=comparison,
            period_id=period_id,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            decision="zero",
            failure_reason="affirmative_zero_evidence_unavailable",
        )
    evidence = max(
        matching,
        key=lambda item: (
            item.filing_date,
            item.source_accession_number,
            item.evidence_id,
        ),
    )
    return RecoveryApplication(
        recommendation_request_id=recommendation.recommendation_request_id,
        recommendation_attempt_number=recommendation.attempt_number,
        company_id=recommendation.company_id,
        period_id=period_id,
        target_metric_name=comparison.target_metric_name,
        statement_type=comparison.statement_type,
        decision="zero",
        status=RECOVERY_APPLICATION_SUCCEEDED,
        failure_reason=None,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        value_numeric=Decimal("0"),
        unit=evidence.unit,
        period_type=evidence.period_type,
        start_date=evidence.start_date,
        end_date=evidence.end_date,
        filing_date=evidence.filing_date,
        source_raw_fact_ids=(evidence.raw_fact_id,),
        source_accession_numbers=(evidence.source_accession_number,),
        components=(),
        zero_evidence=evidence,
    )


def _component_candidates(
    *,
    precedence: CompanyPrecedenceResult,
    company_id: str,
    taxonomy: str,
    concept: str,
    fiscal_year: int,
    fiscal_period: str,
) -> tuple[PrecedenceSelectedObservation, ...]:
    return tuple(
        selected
        for selected in precedence.selected_observations
        if (
            selected.observation.fact.taxonomy.casefold()
            == taxonomy.casefold()
            and selected.observation.fact.concept == concept
            and selected.observation.fact.fiscal_year == fiscal_year
            and selected.observation.fact.fiscal_period == fiscal_period
            and same_cik(selected.observation.fact.cik, company_id)
            and _selected_fact_has_usable_context(selected)
        )
    )


def _selected_fact_has_usable_context(
    selected: PrecedenceSelectedObservation,
) -> bool:
    fact = selected.observation.fact
    return not (
        fact.value is None
        or fact.is_numeric is False
        or not fact.is_consolidated
        or fact.dimensions
    )


def _component_incompatibility(
    components: list[RecoveryComponentApplication],
    *,
    statement_type: str,
    target_metric_name: str,
    expected_start_date: date | None,
    expected_end_date: date,
) -> str | None:
    expected_period_type = _expected_period_type(statement_type)
    first = components[0]
    if (
        expected_period_type is not None
        and first.period_type != expected_period_type
    ):
        return "component_period_type_incompatible"
    if _unit_family(first.unit) != _target_unit_family(
        target_metric_name,
        statement_type,
    ):
        return "component_unit_family_incompatible"
    if (
        first.start_date != expected_start_date
        or first.end_date != expected_end_date
    ):
        return "component_actual_period_incompatible"
    for component in components[1:]:
        if (
            component.start_date != first.start_date
            or component.end_date != first.end_date
            or component.period_type != first.period_type
        ):
            return "component_actual_period_incompatible"
        if component.unit.casefold() != first.unit.casefold():
            return "component_unit_incompatible"
    return None


def _invalid_application(
    *,
    recommendation: SemanticRecommendationRecord,
    comparison: SemanticTargetComparison,
    period_id: str,
    fiscal_year: int,
    fiscal_period: str,
    decision: str,
    failure_reason: str,
    components: tuple[RecoveryComponentApplication, ...] = (),
) -> RecoveryApplication:
    return RecoveryApplication(
        recommendation_request_id=recommendation.recommendation_request_id,
        recommendation_attempt_number=recommendation.attempt_number,
        company_id=recommendation.company_id,
        period_id=period_id,
        target_metric_name=comparison.target_metric_name,
        statement_type=comparison.statement_type,
        decision=decision,
        status=RECOVERY_APPLICATION_INVALID,
        failure_reason=failure_reason,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        value_numeric=None,
        unit=None,
        period_type=None,
        start_date=None,
        end_date=None,
        filing_date=None,
        source_raw_fact_ids=tuple(
            sorted(component.raw_fact_id for component in components)
        ),
        source_accession_numbers=tuple(
            sorted(
                {
                    component.accession_number
                    for component in components
                }
            )
        ),
        components=components,
        zero_evidence=None,
    )


def _canonical_decision(
    comparison: SemanticTargetComparison,
) -> dict[str, Any]:
    if comparison.unanimous_canonical_json is None:
        return {}
    value = json.loads(comparison.unanimous_canonical_json)
    if not isinstance(value, dict):
        return {}
    if (
        value.get("target_metric_name") != comparison.target_metric_name
        or value.get("statement_type") != comparison.statement_type
    ):
        return {}
    return value


def _packet_has_zero_concept(
    packet: dict[str, Any],
    evidence: AffirmativeZeroEvidence,
) -> bool:
    return any(
        isinstance(concept, dict)
        and concept.get("evidence_id") == evidence.evidence_id
        and str(concept.get("taxonomy") or "").casefold()
        == evidence.taxonomy.casefold()
        and concept.get("concept") == evidence.concept
        and concept.get("component_eligible") is True
        for concept in packet.get("concepts", [])
    )


def _zero_evidence_matches_precedence(
    precedence: CompanyPrecedenceResult,
    evidence: AffirmativeZeroEvidence,
) -> bool:
    matches = tuple(
        selected
        for selected in precedence.selected_observations
        if _selected_matches_zero_evidence(selected, evidence)
    )
    return len(matches) == 1


def _selected_matches_zero_evidence(
    selected: PrecedenceSelectedObservation,
    evidence: AffirmativeZeroEvidence,
) -> bool:
    fact = selected.observation.fact
    return (
        selected.observation.raw_fact_id == evidence.raw_fact_id
        and selected.observation.arelle_fact_id
        == evidence.arelle_fact_id
        and bool(evidence.arelle_fact_id)
        and selected.accession_number
        == evidence.source_accession_number
        and selected.filing_date == evidence.filing_date
        and same_cik(fact.cik, evidence.company_id)
        and fact.taxonomy.casefold() == evidence.taxonomy.casefold()
        and fact.concept == evidence.concept
        and fact.value == evidence.value_numeric == Decimal("0")
        and fact.source == evidence.source_system
        and fact.fiscal_year == evidence.fiscal_year
        and fact.fiscal_period == evidence.fiscal_period
        and fact.unit.casefold() == evidence.unit.casefold()
        and fact.period_type == evidence.period_type
        and fact.start_date == evidence.start_date
        and fact.end_date == evidence.end_date
        and fact.dimensions == evidence.dimensions
        and fact.is_consolidated == evidence.is_consolidated
        and not _blocking_fact_diagnostics(selected)
    )


def _zero_period_type_is_compatible(
    period_type: str,
    statement_type: str,
) -> bool:
    expected = _expected_period_type(statement_type)
    return expected is None or period_type == expected


def _expected_period_type(statement_type: str) -> str | None:
    return (
        "instant"
        if statement_type == "balance_sheet"
        else "duration"
        if statement_type
        in {"cash_flow", "cash_flow_statement", "income_statement", "shares"}
        else None
    )


def _target_unit_family(
    target_metric_name: str,
    statement_type: str,
) -> str:
    metric_name = target_metric_name.casefold()
    if metric_name.endswith("eps") or "_eps" in metric_name:
        return "per_share"
    if "shares" in metric_name or statement_type == "shares":
        return "shares"
    return "monetary"


def _unit_family(unit: str) -> str:
    normalized = unit.strip().casefold()
    if "/" in normalized and "share" in normalized:
        return "per_share"
    if normalized in {"share", "shares"}:
        return "shares"
    currency = normalized.rsplit(":", 1)[-1]
    if "/" not in normalized and len(currency) == 3 and currency.isalpha():
        return "monetary"
    return "other"


def _blocking_fact_diagnostics(
    selected: PrecedenceSelectedObservation,
) -> tuple[ArelleDiagnosticRecord, ...]:
    arelle_fact_id = selected.observation.arelle_fact_id
    if arelle_fact_id is None:
        return ()
    return tuple(
        diagnostic
        for diagnostic in selected.reconciliation.blocking_diagnostics
        if (
            arelle_fact_id in diagnostic.fact_ids
            and diagnostic.severity.casefold()
            in {"error", "critical", "fatal"}
        )
    )


def _component_diagnostic(
    diagnostic: ArelleDiagnosticRecord,
) -> RecoveryComponentDiagnostic:
    return RecoveryComponentDiagnostic(
        severity=diagnostic.severity,
        code=diagnostic.code,
        message=diagnostic.message,
        fact_ids=diagnostic.fact_ids,
        relationship_ids=diagnostic.relationship_ids,
        source_references=diagnostic.source_references,
    )


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        sorted(
            {
                clean
                for item in value
                if (clean := str(item or "").strip())
            }
        )
    )


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _date_value(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
