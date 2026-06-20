"""Normalize issuer-extension and dimensional facts from an Arelle model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from arelle import XbrlConst

from src.processing.periods import classify_period, validate_period
from src.processing.quality import (
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    add_quality_flag,
)
from src.processing.xbrl_normalizer import NormalizedFact, find_duplicate_facts

INLINE_XBRL_SOURCE = "sec_inline_xbrl"

_STANDARD_NAMESPACE_PREFIXES = (
    "http://fasb.org/",
    "https://fasb.org/",
    "http://xbrl.sec.gov/",
    "https://xbrl.sec.gov/",
    "http://www.xbrl.org/",
    "https://www.xbrl.org/",
    "http://www.sec.gov/",
    "https://www.sec.gov/",
)


@dataclass(frozen=True)
class InlineXbrlExtractionResult:
    """Normalized facts and diagnostics from one Inline XBRL filing."""

    facts: tuple[NormalizedFact, ...]
    total_facts_seen: int
    custom_fact_count: int
    dimensional_fact_count: int
    model_error_count: int


def normalize_inline_xbrl_model(
    model_xbrl: Any,
    *,
    cik: str,
    entity_name: str | None,
    form: str,
    filing_date: date,
    accession_number: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
    source_document: str,
) -> InlineXbrlExtractionResult:
    """Preserve custom and dimensional facts absent from companyfacts."""
    facts: list[NormalizedFact] = []
    custom_fact_count = 0
    dimensional_fact_count = 0
    for model_fact in model_xbrl.facts:
        context = model_fact.context
        qname = model_fact.qname
        if context is None or qname is None:
            continue
        namespace_uri = str(qname.namespaceURI or "")
        dimensions = _context_dimensions(context)
        is_custom = _is_custom_namespace(namespace_uri)
        if not is_custom and not dimensions:
            continue
        if is_custom:
            custom_fact_count += 1
        if dimensions:
            dimensional_fact_count += 1
        facts.append(
            _normalize_model_fact(
                model_fact,
                cik=cik,
                entity_name=entity_name,
                form=form,
                filing_date=filing_date,
                accession_number=accession_number,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                document_url=source_document,
                namespace_uri=namespace_uri,
                dimensions=dimensions,
            )
        )
    normalized = find_duplicate_facts(facts)
    return InlineXbrlExtractionResult(
        facts=tuple(normalized),
        total_facts_seen=len(model_xbrl.facts),
        custom_fact_count=custom_fact_count,
        dimensional_fact_count=dimensional_fact_count,
        model_error_count=len(model_xbrl.errors),
    )


def _normalize_model_fact(
    model_fact: Any,
    *,
    cik: str,
    entity_name: str | None,
    form: str,
    filing_date: date,
    accession_number: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
    document_url: str,
    namespace_uri: str,
    dimensions: tuple[tuple[str, str], ...],
) -> NormalizedFact:
    concept = model_fact.concept
    context = model_fact.context
    is_numeric = bool(concept is not None and concept.isNumeric)
    value_raw = None if model_fact.isNil else model_fact.value
    value = _numeric_value(model_fact) if is_numeric else None
    flags: tuple[str, ...] = ()
    if value_raw is None or str(value_raw).strip() == "":
        flags = add_quality_flag(flags, MISSING_VALUE)
    elif value is None:
        flags = add_quality_flag(flags, NON_NUMERIC_VALUE)

    start_date, end_date = _context_period(context)
    for flag in validate_period(start_date, end_date):
        flags = add_quality_flag(flags, flag)

    qname = model_fact.qname
    taxonomy = str(qname.prefix or _namespace_label(namespace_uri))
    label = concept.label(lang="en", strip=True) if concept is not None else None
    description = (
        concept.genLabel(
            role=XbrlConst.documentationLabel,
            lang="en",
            strip=True,
        )
        if concept is not None
        else None
    )
    return NormalizedFact(
        cik=cik,
        entity_name=entity_name,
        taxonomy=taxonomy,
        concept=str(qname.localName),
        label=label,
        description=description,
        unit=_unit_text(model_fact.unit),
        value_raw=value_raw,
        value=value,
        start_date=start_date,
        end_date=end_date,
        period_type=classify_period(start_date, end_date),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=filing_date,
        accession_number=accession_number,
        frame=None,
        source=INLINE_XBRL_SOURCE,
        quality_flags=flags,
        namespace_uri=namespace_uri or None,
        context_id=str(model_fact.contextID or "") or None,
        dimensions=dimensions,
        is_consolidated=not dimensions,
        source_document=document_url,
        balance=(str(concept.balance) if concept is not None and concept.balance else None),
        is_numeric=is_numeric,
    )


def _numeric_value(model_fact: Any) -> Decimal | None:
    if model_fact.isNil:
        return None
    try:
        return Decimal(str(model_fact.xValue))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _context_period(context: Any) -> tuple[date | None, date | None]:
    if context.isInstantPeriod:
        return None, context.instantDate
    if context.isStartEndPeriod:
        return context.startDatetime.date(), context.endDate
    return None, None


def _context_dimensions(context: Any) -> tuple[tuple[str, str], ...]:
    dimensions: list[tuple[str, str]] = []
    for dimension_qname, dimension_value in context.qnameDims.items():
        if dimension_value.isExplicit:
            member = str(dimension_value.memberQname)
        else:
            typed_member = dimension_value.typedMember
            member = str(getattr(typed_member, "xValue", None) or typed_member.stringValue)
        dimensions.append((str(dimension_qname), member))
    return tuple(sorted(dimensions))


def _unit_text(unit: Any) -> str:
    if unit is None:
        return "none"
    numerator, denominator = unit.measures
    numerator_text = "*".join(_measure_text(measure) for measure in numerator)
    if not denominator:
        return numerator_text or "none"
    denominator_text = "*".join(_measure_text(measure) for measure in denominator)
    return f"{numerator_text}/{denominator_text}"


def _measure_text(measure: Any) -> str:
    return str(measure.localName or measure)


def _is_custom_namespace(namespace_uri: str) -> bool:
    return bool(namespace_uri) and not namespace_uri.startswith(_STANDARD_NAMESPACE_PREFIXES)


def _namespace_label(namespace_uri: str) -> str:
    label = namespace_uri.rstrip("/").rsplit("/", 1)[-1]
    return label or "unknown"
