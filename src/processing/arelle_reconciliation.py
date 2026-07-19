"""Deterministic accession-level reconciliation for the Plan 203 proof."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.processing.arelle_records import ArelleFilingResult, ExtractedFact, UnitKey
from src.processing.xbrl_normalizer import NormalizedFact


@dataclass(frozen=True, order=True)
class ReconciliationKey:
    """Taxonomy-family identity shared by both ingestion sources."""

    taxonomy: str
    concept_local_name: str
    period_type: str
    start_date: str | None
    end_date: str | None
    unit: str


@dataclass(frozen=True)
class ReconciliationConflict:
    """One unambiguous context whose two sources disagree on value."""

    key: ReconciliationKey
    arelle_value: str | None
    companyfacts_value: str | None


@dataclass(frozen=True)
class ArelleReconciliationSummary:
    """Evidence counts for one accession, without choosing a winning source."""

    accession_number: str
    arelle_facts_considered: int
    companyfacts_facts_considered: int
    exact_matches: int
    value_conflicts: int
    ambiguous_keys: int
    arelle_only_facts: int
    companyfacts_only_facts: int
    conflicts: tuple[ReconciliationConflict, ...] = ()


def reconcile_arelle_with_companyfacts(
    result: ArelleFilingResult,
    companyfacts: list[NormalizedFact] | tuple[NormalizedFact, ...],
    *,
    max_conflicts: int = 100,
) -> ArelleReconciliationSummary:
    """Compare consolidated observations for the result's accession.

    SEC Company Facts does not expose a versioned namespace URI, so overlap is
    keyed by taxonomy family and local name. The full Arelle namespace remains
    present on its source fact for lineage and later diagnostics.
    """
    if max_conflicts < 0:
        raise ValueError("max_conflicts cannot be negative")

    accession = _normalize_accession(result.accession_number)
    arelle_groups: dict[ReconciliationKey, list[ExtractedFact]] = defaultdict(list)
    for fact in result.facts:
        if fact.context_key.dimensions:
            continue
        arelle_groups[_arelle_key(fact)].append(fact)

    company_groups: dict[ReconciliationKey, list[NormalizedFact]] = defaultdict(list)
    for fact in companyfacts:
        if not fact.is_consolidated or fact.dimensions:
            continue
        if fact.accession_number is None:
            continue
        if _normalize_accession(fact.accession_number) != accession:
            continue
        company_groups[_companyfacts_key(fact)].append(fact)

    exact_matches = 0
    value_conflicts = 0
    ambiguous_keys = 0
    arelle_only_facts = 0
    companyfacts_only_facts = 0
    conflicts: list[ReconciliationConflict] = []

    for key in sorted(set(arelle_groups) | set(company_groups)):
        arelle_values = arelle_groups.get(key, [])
        company_values = company_groups.get(key, [])
        if not arelle_values:
            companyfacts_only_facts += len(company_values)
            continue
        if not company_values:
            arelle_only_facts += len(arelle_values)
            continue
        if len(arelle_values) != 1 or len(company_values) != 1:
            ambiguous_keys += 1
            continue

        arelle_value = arelle_values[0].value
        company_value = _companyfacts_value(company_values[0])
        if _values_equal(arelle_value, company_value):
            exact_matches += 1
        else:
            value_conflicts += 1
            if len(conflicts) < max_conflicts:
                conflicts.append(
                    ReconciliationConflict(
                        key=key,
                        arelle_value=arelle_value,
                        companyfacts_value=company_value,
                    )
                )

    return ArelleReconciliationSummary(
        accession_number=result.accession_number,
        arelle_facts_considered=sum(len(items) for items in arelle_groups.values()),
        companyfacts_facts_considered=sum(
            len(items) for items in company_groups.values()
        ),
        exact_matches=exact_matches,
        value_conflicts=value_conflicts,
        ambiguous_keys=ambiguous_keys,
        arelle_only_facts=arelle_only_facts,
        companyfacts_only_facts=companyfacts_only_facts,
        conflicts=tuple(conflicts),
    )


def _arelle_key(fact: ExtractedFact) -> ReconciliationKey:
    context = fact.context_key
    end_date = context.instant_date if context.period_type == "instant" else context.end_date
    return ReconciliationKey(
        taxonomy=_arelle_taxonomy_family(fact),
        concept_local_name=fact.concept_key.local_name,
        period_type=context.period_type,
        start_date=context.start_date,
        end_date=end_date,
        unit=_arelle_unit(fact.unit_key),
    )


def _companyfacts_key(fact: NormalizedFact) -> ReconciliationKey:
    return ReconciliationKey(
        taxonomy=fact.taxonomy,
        concept_local_name=fact.concept,
        period_type=fact.period_type,
        start_date=fact.start_date.isoformat() if fact.start_date is not None else None,
        end_date=fact.end_date.isoformat() if fact.end_date is not None else None,
        unit=fact.unit,
    )


def _arelle_unit(unit: UnitKey | None) -> str:
    if unit is None:
        return ""
    numerator = "*".join(item.local_name for item in unit.numerator)
    if not unit.denominator:
        return numerator
    denominator = "*".join(item.local_name for item in unit.denominator)
    return f"{numerator}/{denominator}"


def _arelle_taxonomy_family(fact: ExtractedFact) -> str:
    namespace = fact.concept_key.namespace_uri.lower().rstrip("/")
    for family in ("us-gaap", "dei", "country", "ecd", "srt"):
        if namespace.endswith(f"/{family}") or f"/{family}/" in namespace:
            return family
    if fact.concept_key.prefix:
        return fact.concept_key.prefix
    return fact.concept_key.namespace_uri


def _companyfacts_value(fact: NormalizedFact) -> str | None:
    if fact.value is not None:
        return str(fact.value)
    if fact.value_raw is None:
        return None
    return str(fact.value_raw)


def _values_equal(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return Decimal(left) == Decimal(right)
    except InvalidOperation:
        return left.strip() == right.strip()


def _normalize_accession(value: str) -> str:
    return value.strip().replace("-", "")
