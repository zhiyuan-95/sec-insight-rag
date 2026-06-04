"""Normalize SEC companyfacts JSON into auditable financial fact records."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from src.processing.concepts import COMMON_GAAP_CONCEPTS, DEFAULT_FORMS, DEFAULT_TAXONOMIES, SUPPORTED_REPORT_FORMS
from src.processing.errors import XbrlPayloadError
from src.processing.periods import classify_period, parse_sec_date, validate_period
from src.processing.quality import (
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    INVALID_DATE,
    MISSING_ACCESSION_NUMBER,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
    add_quality_flag,
)


@dataclass(frozen=True)
class NormalizedFact:
    """A normalized SEC companyfacts fact with source metadata."""

    cik: str
    entity_name: str | None
    taxonomy: str
    concept: str
    label: str | None
    description: str | None
    unit: str
    value_raw: object
    value: Decimal | None
    start_date: date | None
    end_date: date | None
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    form: str | None
    filed_date: date | None
    accession_number: str | None
    frame: str | None
    source: str
    quality_flags: tuple[str, ...] = ()


def normalize_companyfacts(
    payload: dict[str, Any],
    concepts: set[str] | None = None,
    forms: set[str] | None = DEFAULT_FORMS,
    taxonomies: set[str] | None = DEFAULT_TAXONOMIES,
) -> list[NormalizedFact]:
    """Normalize a SEC companyfacts payload into fact records."""
    cik = _normalize_cik(_required(payload, "cik", "companyfacts payload"))
    entity_name = _optional_text(payload.get("entityName"))
    facts_payload = payload.get("facts")
    if not isinstance(facts_payload, dict):
        raise XbrlPayloadError("companyfacts payload missing facts object")

    requested_forms = {form.upper() for form in forms} if forms is not None else None
    requested_taxonomies = set(taxonomies) if taxonomies is not None else None
    requested_concepts = COMMON_GAAP_CONCEPTS if concepts is None else concepts

    normalized: list[NormalizedFact] = []
    for taxonomy, taxonomy_payload in facts_payload.items():
        if not isinstance(taxonomy_payload, dict):
            raise XbrlPayloadError(f"taxonomy payload was not an object: {taxonomy}")
        if requested_taxonomies is not None and taxonomy not in requested_taxonomies:
            continue
        for concept, concept_payload in taxonomy_payload.items():
            if concept not in requested_concepts:
                continue
            if not isinstance(concept_payload, dict):
                raise XbrlPayloadError(f"concept payload was not an object: {concept}")
            units_payload = concept_payload.get("units")
            if not isinstance(units_payload, dict):
                raise XbrlPayloadError(f"concept payload missing units object: {concept}")
            ambiguous_unit = len(units_payload) > 1
            for unit, fact_entries in units_payload.items():
                if not isinstance(fact_entries, list):
                    raise XbrlPayloadError(f"unit facts were not a list: {concept}/{unit}")
                for fact_entry in fact_entries:
                    if not isinstance(fact_entry, dict):
                        raise XbrlPayloadError(f"fact entry was not an object: {concept}/{unit}")
                    fact = normalize_fact_entry(
                        cik=cik,
                        entity_name=entity_name,
                        taxonomy=str(taxonomy),
                        concept=str(concept),
                        concept_payload=concept_payload,
                        unit=str(unit),
                        fact_entry=fact_entry,
                        ambiguous_unit=ambiguous_unit,
                    )
                    if requested_forms is not None and (fact.form is None or fact.form.upper() not in requested_forms):
                        continue
                    normalized.append(fact)

    return find_duplicate_facts(normalized)


def normalize_fact_entry(
    *,
    cik: str,
    entity_name: str | None,
    taxonomy: str,
    concept: str,
    concept_payload: dict[str, Any],
    unit: str,
    fact_entry: dict[str, Any],
    ambiguous_unit: bool = False,
) -> NormalizedFact:
    """Normalize one SEC companyfacts fact object."""
    flags: tuple[str, ...] = ()
    value_raw = fact_entry.get("val")
    value = _parse_decimal(value_raw)
    if "val" not in fact_entry or value_raw is None:
        flags = add_quality_flag(flags, MISSING_VALUE)
    elif value is None:
        flags = add_quality_flag(flags, NON_NUMERIC_VALUE)

    start_date = parse_sec_date(fact_entry.get("start"))
    end_date = parse_sec_date(fact_entry.get("end"))
    filed_date = parse_sec_date(fact_entry.get("filed"))
    flags = (*flags, *validate_period(start_date, end_date))
    if _has_invalid_date(fact_entry, "start", start_date) or _has_invalid_date(fact_entry, "end", end_date):
        flags = add_quality_flag(flags, INVALID_DATE)
    if _has_invalid_date(fact_entry, "filed", filed_date):
        flags = add_quality_flag(flags, INVALID_DATE)

    form = _optional_text(fact_entry.get("form"))
    if form is None:
        flags = add_quality_flag(flags, MISSING_FORM)
    elif form.upper() not in SUPPORTED_REPORT_FORMS:
        flags = add_quality_flag(flags, UNSUPPORTED_FORM)

    accession_number = _optional_text(fact_entry.get("accn"))
    if accession_number is None:
        flags = add_quality_flag(flags, MISSING_ACCESSION_NUMBER)

    if ambiguous_unit:
        flags = add_quality_flag(flags, AMBIGUOUS_UNIT)

    return NormalizedFact(
        cik=cik,
        entity_name=entity_name,
        taxonomy=taxonomy,
        concept=concept,
        label=_optional_text(concept_payload.get("label")),
        description=_optional_text(concept_payload.get("description")),
        unit=unit,
        value_raw=value_raw,
        value=value,
        start_date=start_date,
        end_date=end_date,
        period_type=classify_period(start_date, end_date),
        fiscal_year=_parse_int(fact_entry.get("fy")),
        fiscal_period=_optional_text(fact_entry.get("fp")),
        form=form.upper() if form is not None else None,
        filed_date=filed_date,
        accession_number=accession_number,
        frame=_optional_text(fact_entry.get("frame")),
        source="sec_companyfacts",
        quality_flags=flags,
    )


def find_duplicate_facts(facts: list[NormalizedFact]) -> list[NormalizedFact]:
    """Mark facts that share the same identifying SEC dimensions."""
    positions_by_key: dict[tuple[object, ...], list[int]] = {}
    for index, fact in enumerate(facts):
        positions_by_key.setdefault(_duplicate_key(fact), []).append(index)

    duplicate_positions = {
        index
        for positions in positions_by_key.values()
        if len(positions) > 1
        for index in positions
    }
    if not duplicate_positions:
        return facts

    flagged = list(facts)
    for index in duplicate_positions:
        fact = flagged[index]
        flagged[index] = replace(fact, quality_flags=add_quality_flag(fact.quality_flags, DUPLICATE_FACT))
    return flagged


def _duplicate_key(fact: NormalizedFact) -> tuple[object, ...]:
    return (
        fact.cik,
        fact.taxonomy,
        fact.concept,
        fact.unit,
        fact.start_date,
        fact.end_date,
        fact.fiscal_year,
        fact.fiscal_period,
        fact.form,
        fact.accession_number,
        fact.frame,
    )


def _normalize_cik(value: object) -> str:
    text = str(value).strip()
    if not text.isdigit():
        raise XbrlPayloadError(f"companyfacts cik must be numeric: {text}")
    if len(text) > 10:
        raise XbrlPayloadError(f"companyfacts cik is longer than 10 digits: {text}")
    return text.zfill(10)


def _required(payload: dict[str, Any], field: str, context: str) -> object:
    if field not in payload:
        raise XbrlPayloadError(f"{context} missing {field}")
    return payload[field]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _has_invalid_date(fact_entry: dict[str, Any], field: str, parsed: date | None) -> bool:
    raw = fact_entry.get(field)
    return raw is not None and str(raw).strip() != "" and parsed is None
