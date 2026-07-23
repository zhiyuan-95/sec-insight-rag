"""Fiscal-period industry classification orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from src.analyze.industry_classification import (
    DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL,
    BusinessSectionSource,
    IndustryJsonGenerator,
    classify_company_industry_labels,
)
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    LABEL_STATUS_ASSIGNED,
    industry_label_assignments_for_company,
)
from src.storage.industry_labels_repository import (
    CompanyIndustryLabelRepository,
    StoredFiscalPeriodIndustryLabelSnapshot,
)


@dataclass(frozen=True)
class FiscalPeriodIndustryClassificationSource:
    """Original annual filing evidence for one primary fiscal period."""

    form: str
    fiscal_year: int
    fiscal_period: str
    business_section: BusinessSectionSource


def classify_and_persist_fiscal_period_industry_labels(
    *,
    repository: CompanyIndustryLabelRepository,
    company_id: int,
    ticker: str,
    cik: str,
    company_name: str | None,
    sources: Sequence[FiscalPeriodIndustryClassificationSource],
    api_key: str | None,
    model: str = DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL,
    sic: str | None = None,
    sic_description: str | None = None,
    observed_concepts: Iterable[str] = (),
    generate_json: IndustryJsonGenerator | None = None,
) -> tuple[StoredFiscalPeriodIndustryLabelSnapshot, ...]:
    """Classify each unsnapshotted original 10-K and persist its decision once."""
    observed_concept_values = tuple(observed_concepts)
    source_controlled = industry_label_assignments_for_company(
        ticker,
        cik,
        sic=sic,
        sic_description=sic_description,
        observed_concepts=observed_concept_values,
    )
    ordered_sources = sorted(
        sources,
        key=lambda source: (
            source.fiscal_year,
            source.fiscal_period,
            source.business_section.accession_number,
        ),
    )
    for source in ordered_sources:
        if source.form.strip().upper() != "10-K":
            continue
        accession_number = source.business_section.accession_number
        existing = repository.get_period_snapshot(
            company_id=company_id,
            accession_number=accession_number,
            fiscal_year=source.fiscal_year,
            fiscal_period=source.fiscal_period,
        )
        if existing is not None:
            continue

        try:
            assignment = classify_company_industry_labels(
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                business_section=source.business_section,
                sic=sic,
                sic_description=sic_description,
                api_key=api_key,
                model=model,
                generate_json=generate_json,
            )
        except Exception as exc:
            assignment = replace(
                source_controlled,
                assignment_reason=(
                    "Gemini industry classification failed; using the existing "
                    f"source-controlled fallback. {source_controlled.assignment_reason}"
                ),
                supporting_evidence=(
                    *source_controlled.supporting_evidence,
                    f"Gemini classification failure: {type(exc).__name__}",
                ),
            )
        else:
            if (
                not assignment.assigned_industry_labels
                and source_controlled.label_status == LABEL_STATUS_ASSIGNED
                and source_controlled.assigned_industry_labels
            ):
                assignment = source_controlled
        repository.insert_period_snapshot(
            _snapshot_from_assignment(
                company_id=company_id,
                source=source,
                assignment=assignment,
            )
        )
    return repository.list_period_snapshots(company_id)


def _snapshot_from_assignment(
    *,
    company_id: int,
    source: FiscalPeriodIndustryClassificationSource,
    assignment: CompanyIndustryLabelAssignment,
) -> StoredFiscalPeriodIndustryLabelSnapshot:
    return StoredFiscalPeriodIndustryLabelSnapshot(
        company_id=company_id,
        accession_number=source.business_section.accession_number,
        fiscal_year=source.fiscal_year,
        fiscal_period=source.fiscal_period,
        assigned_industry_labels=assignment.assigned_industry_labels,
        assignment_source=assignment.assignment_source,
        assignment_reason=assignment.assignment_reason,
        label_status=assignment.label_status,
        confidence=assignment.confidence,
        evidence=assignment.supporting_evidence,
        classifier_version=assignment.classifier_version,
        reviewed_at=assignment.reviewed_at or None,
    )
