"""Company-level ingestion orchestration."""

from __future__ import annotations

import shutil
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from src.analyze.industry_classification import (
    BusinessSectionSource,
    GEMINI_INDUSTRY_CLASSIFIER_VERSION,
    classify_company_industry_labels,
    stored_label_source_accessions,
)
from src.indicators import calculate_indicators
from src.ingestion.companyfacts import get_companyfacts
from src.ingestion.errors import SecIngestionError
from src.ingestion.filings import FilingMetadata, download_filing_document, list_recent_filings
from src.ingestion.inline_xbrl import get_inline_xbrl_facts
from src.ingestion.refresh_policy import next_business_day, next_check_date_for_filing
from src.ingestion.sec_client import SecClient
from src.ingestion.submissions import get_company_submissions
from src.ingestion.tickers import load_ticker_mapping, resolve_ticker_to_cik
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    LABEL_STATUS_ASSIGNED,
    industry_label_assignments_for_company,
)
from src.processing import (
    INLINE_XBRL_SOURCE,
    BaseMetricRecord,
    IndustryFactTarget,
    InlineXbrlExtractionError,
    NormalizedFact,
    SemanticMappingCandidate,
    active_accessions_for_facts,
    active_period_keys,
    active_period_keys_from_periods,
    canonical_metric_targets,
    generate_semantic_mapping_candidates,
    mapping_candidates_by_key,
    mapping_candidates_by_concept,
    map_raw_facts_to_base_metrics,
    missing_metric_targets,
    normalize_companyfacts,
)
from src.storage import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    MAPPING_STATUS_CANDIDATE,
    CompanyRecord,
    CompanyIndustryLabelRepository,
    CompanyRepository,
    ConceptMappingRecord,
    ConceptMappingRepository,
    FilingRecord,
    FilingRepository,
    FinancialIndicatorRepository,
    FinancialMetric,
    FinancialMetricRepository,
    RawFactRepository,
    RetrievalRepository,
    StoredCompanyIndustryLabel,
    connect_sqlite,
)
from src.retrieval.errors import EmptyFilingTextError, FilingParseError
from src.retrieval.parser import parse_filing_html

if TYPE_CHECKING:
    from src.config import Settings

PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class CompanyIngestionResult:
    """Result summary for one company ingestion run."""

    ticker: str
    cik: str
    filings: tuple[FilingMetadata, ...]
    downloaded_filings: tuple[Path | None, ...]
    normalized_fact_count: int
    stored_fact_count: int
    warnings: tuple[str, ...] = ()
    company_id: int | None = None
    stored_filing_count: int = 0
    stored_metric_count: int = 0
    active_metric_count: int = 0
    stored_indicator_count: int = 0
    active_indicator_count: int = 0
    status: str = "updated"
    sec_checked: bool = True
    refresh_due_10k: bool | None = None
    refresh_due_10q: bool | None = None
    inline_xbrl_fact_count: int = 0
    semantic_mapping_candidate_count: int = 0
    approved_mapping_count: int = 0
    industry_label_count: int = 0


@dataclass(frozen=True)
class CompanyDeletionResult:
    """Summary of deleted local data for one ingested company."""

    identifier: str
    cik: str | None
    company_id: int | None
    company_found: bool
    indicator_rows_deleted: int
    metric_rows_deleted: int
    filing_rows_deleted: int
    raw_fact_rows_deleted: int
    company_rows_deleted: int
    filing_paths_deleted: tuple[Path, ...] = ()
    filing_paths_skipped: tuple[Path, ...] = ()
    message: str | None = None
    retrieval_chunk_rows_deleted: int = 0
    retrieval_state_rows_deleted: int = 0
    retrieval_paths_deleted: tuple[Path, ...] = ()
    retrieval_paths_skipped: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _FilingPeriodSummary:
    fiscal_year: int | None
    fiscal_period: str | None
    report_date: date | None


@dataclass(frozen=True)
class _ApprovedCompanyConceptProfile:
    """Approved mapping state reusable for one company ingestion."""

    records: tuple[ConceptMappingRecord, ...]
    mappings: dict[tuple[str, str], IndustryFactTarget]

    @property
    def mapping_count(self) -> int:
        return len(self.mappings)


def ingest_company(ticker: str, settings: Settings) -> CompanyIngestionResult:
    """Ingest or inspect one company using refresh-aware local state."""
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required")

    existing_company = _get_existing_company(settings, normalized_ticker)
    if existing_company is not None:
        refresh_due_10k, refresh_due_10q = _company_refresh_due(existing_company)
        mapping_enrichment_due = _company_mapping_enrichment_due(
            settings,
            existing_company,
        )
        if not refresh_due_10k and not refresh_due_10q and not mapping_enrichment_due:
            return _build_local_ingestion_result(
                settings=settings,
                company=existing_company,
                status="reused_local",
                sec_checked=False,
                refresh_due_10k=refresh_due_10k,
                refresh_due_10q=refresh_due_10q,
            )

    try:
        return _ingest_company_from_sec(
            normalized_ticker=normalized_ticker,
            settings=settings,
            existing_company=existing_company,
        )
    except SecIngestionError as exc:
        if existing_company is None:
            raise
        refresh_due_10k, refresh_due_10q = _company_refresh_due(existing_company)
        return _build_local_ingestion_result(
            settings=settings,
            company=existing_company,
            status="refresh_failed_using_local_data",
            sec_checked=True,
            refresh_due_10k=refresh_due_10k,
            refresh_due_10q=refresh_due_10q,
            warnings=(f"SEC refresh failed; using existing local data: {exc}",),
        )


def _ingest_company_from_sec(
    *,
    normalized_ticker: str,
    settings: Settings,
    existing_company: CompanyRecord | None,
) -> CompanyIngestionResult:
    client = SecClient(settings.sec_user_agent)
    ticker_mapping = load_ticker_mapping(client)
    cik = resolve_ticker_to_cik(normalized_ticker, ticker_mapping)
    ticker_entry = ticker_mapping[normalized_ticker]

    submissions = get_company_submissions(client, cik)
    companyfacts = get_companyfacts(client, cik)
    normalized_facts = normalize_companyfacts(companyfacts, concepts=None, forms=None, taxonomies=None)
    warnings = list(_collect_quality_warnings(normalized_facts))
    inline_xbrl_fact_count = 0
    semantic_mapping_candidate_count = 0
    approved_mapping_count = 0
    industry_label_count = 0

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        indicator_repository = FinancialIndicatorRepository(connection)
        industry_label_repository = CompanyIndustryLabelRepository(connection)
        concept_mapping_repository = ConceptMappingRepository(connection)

        raw_repository.initialize()
        existing_company = company_repository.get_by_cik(cik)
        existing_filings = (
            filing_repository.list_filings(existing_company.company_id)
            if existing_company is not None and existing_company.company_id is not None
            else []
        )
        existing_filing_by_accession = {
            filing.accession_number: filing
            for filing in existing_filings
        }
        existing_accessions = set(existing_filing_by_accession)

        stored_fact_count = raw_repository.upsert_facts(normalized_facts)
        stored_fact_records = raw_repository.list_fact_records(cik)
        stored_facts = [record.fact for record in stored_fact_records]
        active_keys = active_period_keys(stored_facts)
        active_accessions = active_accessions_for_facts(stored_facts, active_keys)
        recent_filings = tuple(list_recent_filings(submissions, {"10-K", "10-Q"}))
        filings = _select_active_window_filings(recent_filings, active_accessions)
        missing_active_accessions = sorted(active_accessions - {filing.accession_number for filing in filings})
        if missing_active_accessions:
            shown = ", ".join(missing_active_accessions[:5])
            suffix = f" (+{len(missing_active_accessions) - 5} more)" if len(missing_active_accessions) > 5 else ""
            warnings.append(f"Active-window accessions missing from SEC recent filings: {shown}{suffix}")
        downloaded_filings = tuple(
            _download_or_reuse_filing(
                client=client,
                filing=filing,
                base_dir=settings.stock_filings_base_dir,
                existing_filing=existing_filing_by_accession.get(filing.accession_number),
            )
            for filing in filings
        )

        company = company_repository.upsert_company(
            _build_company_record(
                ticker=normalized_ticker,
                cik=cik,
                name=_company_name(companyfacts, submissions, ticker_entry.title),
                submissions=submissions,
                filings=filings,
                facts=stored_facts,
            )
        )
        if company.company_id is None:
            raise RuntimeError(f"Stored company record for CIK {cik} did not include a company_id")
        stored_industry_labels = _resolve_company_industry_labels(
            repository=industry_label_repository,
            company=company,
            ticker=normalized_ticker,
            cik=cik,
            filings=filings,
            downloaded_filings=downloaded_filings,
            observed_concepts=(fact.concept for fact in stored_facts),
            settings=settings,
            warnings=warnings,
        )
        industry_labels = tuple(
            label.industry_label for label in stored_industry_labels
        )
        industry_label_count = len(industry_labels)

        refresh_due_10k, refresh_due_10q = _company_refresh_due(existing_company or company)
        new_accessions = {filing.accession_number for filing in filings} - existing_accessions
        status = _ingestion_status(existing_company, new_accessions)
        if existing_company is not None and status == "checked_no_update":
            override_10k = next_business_day(date.today() + timedelta(days=1)) if refresh_due_10k else None
            override_10q = next_business_day(date.today() + timedelta(days=1)) if refresh_due_10q else None
            company_repository.update_check_state(
                company.company_id,
                next_check_date_10k=override_10k,
                next_check_date_10q=override_10q,
            )
            refreshed_company = company_repository.get_by_cik(cik)
            if refreshed_company is not None:
                company = refreshed_company

        filing_records = _build_filing_records(
            company_id=company.company_id,
            filings=filings,
            downloaded_filings=downloaded_filings,
            facts=stored_facts,
            active_accessions=active_accessions,
        )
        stored_filing_count = filing_repository.upsert_filings(company.company_id, filing_records)
        filing_repository.set_active_window(company.company_id, active_accessions)
        stored_filings = filing_repository.list_filings(company.company_id)
        _, skipped_cleanup_paths = _delete_inactive_filing_artifacts(
            base_dir=settings.stock_filings_base_dir,
            filings=stored_filings,
        )
        if skipped_cleanup_paths:
            warnings.append(
                f"Skipped inactive filing evidence cleanup for {len(skipped_cleanup_paths)} local paths"
            )
        filing_id_by_accession = {
            filing.accession_number: filing.filing_id
            for filing in stored_filings
            if filing.filing_id is not None
        }

        approved_profile = _load_approved_company_concept_profile(
            concept_mapping_repository,
            cik,
            industry_labels,
        )
        approved_mappings = approved_profile.mappings
        approved_mapping_count = approved_profile.mapping_count
        mapping_names = _deterministic_mapping_names(
            industry_labels,
            approved_profile,
        )
        targets = canonical_metric_targets(industry_labels)
        missing_targets = missing_metric_targets(stored_facts, targets, mapping_names)
        should_extract_inline = bool(missing_targets) and (
            bool(new_accessions)
            or not raw_repository.has_source_facts(cik, INLINE_XBRL_SOURCE)
        )
        if should_extract_inline:
            inline_facts = _extract_active_inline_xbrl_facts(
                filings=stored_filings,
                company=company,
                accessions=(new_accessions or active_accessions),
                sec_user_agent=client.user_agent,
                warnings=warnings,
            )
            inline_xbrl_fact_count = raw_repository.upsert_facts(inline_facts)
            if inline_facts:
                stored_fact_records = raw_repository.list_fact_records(cik)
                stored_facts = [record.fact for record in stored_fact_records]

        if missing_targets:
            candidate_facts = [
                fact
                for fact in stored_facts
                if fact.accession_number in active_accessions
            ]
            candidates = generate_semantic_mapping_candidates(
                candidate_facts,
                missing_targets,
                set(mapping_names),
                embedding_model_name=settings.retrieval_embedding_model,
                model_cache_dir=(
                    settings.knowledge_storage_dir / "model_cache" / "fastembed"
                ),
                target_embedding_path=(
                    settings.knowledge_storage_dir
                    / "concept_mapping"
                    / "target_embeddings.json"
                ),
            )
            semantic_mapping_candidate_count = concept_mapping_repository.upsert_mappings(
                _candidate_mapping_records(cik, candidates)
            )

        base_metrics = map_raw_facts_to_base_metrics(
            ((record.raw_fact_id, record.fact) for record in stored_fact_records),
            active_keys,
            industry_labels,
            approved_mappings,
        )
        financial_metrics = _build_financial_metrics(
            company_id=company.company_id,
            base_metrics=base_metrics,
            filing_id_by_accession=filing_id_by_accession,
        )
        stored_metric_count = metric_repository.upsert_metrics(financial_metrics)
        all_metrics = metric_repository.list_metrics(company.company_id, active_only=False)
        active_metric_count = sum(metric.is_active_window for metric in all_metrics)
        stored_indicator_count, active_indicator_count = _refresh_company_indicators(
            company_id=company.company_id,
            available_metrics=all_metrics,
            indicator_repository=indicator_repository,
        )

    return CompanyIngestionResult(
        ticker=normalized_ticker,
        cik=cik,
        filings=filings,
        downloaded_filings=downloaded_filings,
        normalized_fact_count=len(normalized_facts),
        stored_fact_count=stored_fact_count,
        warnings=tuple(warnings),
        company_id=company.company_id,
        stored_filing_count=stored_filing_count,
        stored_metric_count=stored_metric_count,
        active_metric_count=active_metric_count,
        stored_indicator_count=stored_indicator_count,
        active_indicator_count=active_indicator_count,
        status=status,
        sec_checked=True,
        refresh_due_10k=refresh_due_10k,
        refresh_due_10q=refresh_due_10q,
        inline_xbrl_fact_count=inline_xbrl_fact_count,
        semantic_mapping_candidate_count=semantic_mapping_candidate_count,
        approved_mapping_count=approved_mapping_count,
        industry_label_count=industry_label_count,
    )


def _get_existing_company(settings: Settings, normalized_identifier: str) -> CompanyRecord | None:
    if not settings.stock_sql_db_path.exists():
        return None
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        repository = CompanyRepository(connection)
        repository.initialize()
        cik = _cik_from_identifier(normalized_identifier)
        if cik is not None:
            return repository.get_by_cik(cik)
        return repository.get_by_ticker(normalized_identifier)


def _company_refresh_due(company: CompanyRecord) -> tuple[bool, bool]:
    today = date.today()
    return (
        _date_is_due(company.next_check_date_10k, today),
        _date_is_due(company.next_check_date_10q, today),
    )


def _company_mapping_enrichment_due(
    settings: Settings,
    company: CompanyRecord,
) -> bool:
    if company.company_id is None or not settings.stock_sql_db_path.exists():
        return False
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        filing_repository = FilingRepository(connection)
        raw_repository.initialize()
        if raw_repository.has_source_facts(company.cik, INLINE_XBRL_SOURCE):
            return False
        active_filings = filing_repository.list_filings(
            company.company_id,
            {"10-K", "10-Q"},
            active_only=True,
        )
        return any(
            filing.local_path is not None
            and _looks_like_inline_xbrl(filing.local_path)
            for filing in active_filings
        )


def _date_is_due(next_check_date: date | None, today: date) -> bool:
    return next_check_date is None or today >= next_check_date


def _refresh_company_metrics_from_stored_facts(
    *,
    company_id: int,
    stored_fact_records: list,
    stored_filings: list[FilingRecord],
    active_keys: set[tuple[str, int, str]],
    industry_labels: tuple[str, ...],
    approved_mappings: dict[tuple[str, str], IndustryFactTarget],
    metric_repository: FinancialMetricRepository,
) -> int:
    if not stored_fact_records:
        return 0
    filing_id_by_accession = {
        filing.accession_number: filing.filing_id
        for filing in stored_filings
        if filing.filing_id is not None
    }
    base_metrics = map_raw_facts_to_base_metrics(
        ((record.raw_fact_id, record.fact) for record in stored_fact_records),
        active_keys,
        industry_labels,
        approved_mappings,
    )
    financial_metrics = _build_financial_metrics(
        company_id=company_id,
        base_metrics=base_metrics,
        filing_id_by_accession=filing_id_by_accession,
    )
    return metric_repository.upsert_metrics(financial_metrics)


def _refresh_company_indicators(
    *,
    company_id: int,
    available_metrics: list[FinancialMetric],
    indicator_repository: FinancialIndicatorRepository,
) -> tuple[int, int]:
    indicator_repository.deactivate_by_company_id(company_id)
    indicators = calculate_indicators(company_id, available_metrics)
    stored_indicator_count = indicator_repository.upsert_indicators(indicators)
    active_indicator_count = sum(indicator.is_active_window for indicator in indicators)
    return stored_indicator_count, active_indicator_count


def _resolve_company_industry_labels(
    *,
    repository: CompanyIndustryLabelRepository,
    company: CompanyRecord,
    ticker: str,
    cik: str,
    filings: tuple[FilingMetadata, ...],
    downloaded_filings: tuple[Path | None, ...],
    observed_concepts: Iterable[str],
    settings: Settings,
    warnings: list[str],
) -> tuple[StoredCompanyIndustryLabel, ...]:
    if company.company_id is None:
        raise RuntimeError(f"Stored company record for CIK {cik} did not include a company_id")

    stored_labels = repository.list_labels(company.company_id)
    gemini_api_key = (
        settings.gemini_api_key.get_secret_value()
        if settings.gemini_api_key is not None
        else None
    )
    if gemini_api_key:
        business_section = _latest_10k_business_section(
            filings=filings,
            downloaded_filings=downloaded_filings,
            warnings=warnings,
        )
        if business_section is not None and _industry_classification_due(
            stored_labels,
            business_section.accession_number,
        ):
            try:
                assignment = classify_company_industry_labels(
                    ticker=ticker,
                    cik=cik,
                    company_name=company.name,
                    business_section=business_section,
                    sic=company.sic,
                    sic_description=company.sic_description,
                    api_key=gemini_api_key,
                    model=settings.primary_chat_model,
                )
            except Exception as exc:
                warnings.append(
                    "Gemini industry classification skipped; using existing or "
                    f"source-controlled labels: {exc}"
                )
            else:
                if (
                    assignment.label_status == LABEL_STATUS_ASSIGNED
                    and assignment.assigned_industry_labels
                ):
                    _persist_industry_labels(repository, company.company_id, assignment)
                    return repository.list_labels(company.company_id)
                warnings.append(
                    "Gemini industry classification did not meet the keep criteria; "
                    "ignoring Gemini labels and using existing or source-controlled labels."
                )

    if stored_labels:
        return stored_labels

    assignment = industry_label_assignments_for_company(
        ticker,
        cik,
        sic=company.sic,
        sic_description=company.sic_description,
        observed_concepts=observed_concepts,
    )
    _persist_industry_labels(
        repository,
        company.company_id,
        assignment,
    )
    return repository.list_labels(company.company_id)


def _industry_classification_due(
    stored_labels: tuple[StoredCompanyIndustryLabel, ...],
    accession_number: str,
) -> bool:
    if not stored_labels:
        return True
    gemini_labels = tuple(
        label
        for label in stored_labels
        if label.classifier_version == GEMINI_INDUSTRY_CLASSIFIER_VERSION
    )
    if not gemini_labels:
        return True
    return any(
        accession_number not in stored_label_source_accessions(label.evidence)
        for label in gemini_labels
    )


def _latest_10k_business_section(
    *,
    filings: tuple[FilingMetadata, ...],
    downloaded_filings: tuple[Path | None, ...],
    warnings: list[str],
) -> BusinessSectionSource | None:
    candidates = sorted(
        (
            (filing, path)
            for filing, path in zip(filings, downloaded_filings)
            if filing.form.upper() == "10-K" and path is not None
        ),
        key=lambda item: (item[0].filing_date, item[0].accession_number),
        reverse=True,
    )
    for filing, path in candidates:
        try:
            parsed = parse_filing_html(path, "10-K")
        except (EmptyFilingTextError, FilingParseError) as exc:
            warnings.append(
                "Gemini industry classification skipped for "
                f"{filing.accession_number}; 10-K Item 1 Business could not be parsed: {exc}"
            )
            continue
        section = next(
            (section for section in parsed.sections if section.name == "business"),
            None,
        )
        if section is None or not section.text.strip():
            warnings.append(
                "Gemini industry classification skipped for "
                f"{filing.accession_number}; 10-K Item 1 Business was not detected."
            )
            continue
        return BusinessSectionSource(
            accession_number=filing.accession_number,
            filing_date=filing.filing_date,
            local_path=str(path),
            text=section.text,
        )
    return None


def _build_local_ingestion_result(
    *,
    settings: Settings,
    company: CompanyRecord,
    status: str,
    sec_checked: bool,
    refresh_due_10k: bool,
    refresh_due_10q: bool,
    warnings: tuple[str, ...] = (),
) -> CompanyIngestionResult:
    if company.company_id is None:
        raise RuntimeError(f"Stored company record for CIK {company.cik} did not include a company_id")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        indicator_repository = FinancialIndicatorRepository(connection)
        industry_label_repository = CompanyIndustryLabelRepository(connection)
        concept_mapping_repository = ConceptMappingRepository(connection)
        raw_repository.initialize()
        observed_concepts = raw_repository.list_distinct_concepts(company.cik)
        stored_industry_labels = industry_label_repository.list_labels(company.company_id)
        if not stored_industry_labels:
            assignment = industry_label_assignments_for_company(
                company.ticker,
                company.cik,
                sic=company.sic,
                sic_description=company.sic_description,
                observed_concepts=observed_concepts,
            )
            _persist_industry_labels(
                industry_label_repository,
                company.company_id,
                assignment,
            )
            stored_industry_labels = industry_label_repository.list_labels(
                company.company_id
            )
        industry_labels = tuple(
            label.industry_label for label in stored_industry_labels
        )
        approved_profile = _load_approved_company_concept_profile(
            concept_mapping_repository,
            company.cik,
            industry_labels,
        )
        approved_mappings = approved_profile.mappings
        mapped_concepts = set(mapping_candidates_by_concept(industry_labels)) | {
            row.concept for row in approved_profile.records
        }
        stored_fact_records = raw_repository.list_fact_records(company.cik, mapped_concepts)
        active_keys = active_period_keys_from_periods(raw_repository.list_distinct_periods(company.cik))
        stored_filings = filing_repository.list_filings(company.company_id)
        _refresh_company_metrics_from_stored_facts(
            company_id=company.company_id,
            stored_fact_records=stored_fact_records,
            stored_filings=stored_filings,
            active_keys=active_keys,
            industry_labels=industry_labels,
            approved_mappings=approved_mappings,
            metric_repository=metric_repository,
        )
        active_filings = filing_repository.list_filings(company.company_id, {"10-K", "10-Q"}, active_only=True)
        all_metrics = metric_repository.list_metrics(company.company_id, active_only=False)
        active_metric_count = sum(metric.is_active_window for metric in all_metrics)
        stored_indicator_count, active_indicator_count = _refresh_company_indicators(
            company_id=company.company_id,
            available_metrics=all_metrics,
            indicator_repository=indicator_repository,
        )
        all_indicators = indicator_repository.list_indicators(company.company_id, active_only=False)

    filings = tuple(_filing_metadata_from_record(filing) for filing in active_filings)
    downloaded_filings = tuple(filing.local_path for filing in active_filings)
    return CompanyIngestionResult(
        ticker=(company.ticker or "").upper(),
        cik=company.cik,
        filings=filings,
        downloaded_filings=downloaded_filings,
        normalized_fact_count=0,
        stored_fact_count=0,
        warnings=warnings,
        company_id=company.company_id,
        stored_filing_count=len(active_filings),
        stored_metric_count=len(all_metrics),
        active_metric_count=active_metric_count,
        stored_indicator_count=max(len(all_indicators), stored_indicator_count),
        active_indicator_count=active_indicator_count,
        status=status,
        sec_checked=sec_checked,
        refresh_due_10k=refresh_due_10k,
        refresh_due_10q=refresh_due_10q,
        approved_mapping_count=approved_profile.mapping_count,
        industry_label_count=len(industry_labels),
    )


def _persist_industry_labels(
    repository: CompanyIndustryLabelRepository,
    company_id: int,
    assignment: CompanyIndustryLabelAssignment,
) -> int:
    labels = tuple(
        StoredCompanyIndustryLabel(
            company_id=company_id,
            industry_label=industry_label,
            assignment_source=assignment.assignment_source,
            assignment_reason=assignment.assignment_reason,
            status="approved",
            confidence=assignment.confidence,
            evidence=assignment.supporting_evidence,
            classifier_version=assignment.classifier_version or "source_controlled_registry_v1",
            reviewed_at=assignment.reviewed_at or None,
        )
        for industry_label in assignment.assigned_industry_labels
    )
    return repository.replace_labels(company_id, labels)


def _extract_active_inline_xbrl_facts(
    *,
    filings: list[FilingRecord],
    company: CompanyRecord,
    accessions: set[str],
    sec_user_agent: str,
    warnings: list[str],
) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    validation_message_count = 0
    extracted_filing_count = 0
    for filing in filings:
        if not filing.is_active_window or filing.accession_number not in accessions:
            continue
        if filing.local_path is None or not _looks_like_inline_xbrl(filing.local_path):
            continue
        if not filing.document_url:
            warnings.append(
                "Inline XBRL extraction skipped because the filing URL is missing: "
                f"{filing.accession_number}"
            )
            continue
        try:
            result = get_inline_xbrl_facts(
                filing.document_url,
                cik=company.cik,
                entity_name=company.name,
                form=filing.form_type,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                fiscal_year=filing.fiscal_year,
                fiscal_period=filing.fiscal_period,
                sec_user_agent=sec_user_agent,
            )
        except InlineXbrlExtractionError as exc:
            warnings.append(str(exc))
            continue
        extracted_filing_count += 1
        validation_message_count += result.model_error_count
        facts.extend(result.facts)
    if validation_message_count:
        warnings.append(
            "Arelle reported "
            f"{validation_message_count} validation messages across "
            f"{extracted_filing_count} Inline XBRL filings; extracted facts were retained "
            "with source and quality metadata."
        )
    return facts


def _looks_like_inline_xbrl(path: Path) -> bool:
    try:
        with path.open("rb") as filing:
            prefix = filing.read(262_144).lower()
    except OSError:
        return False
    return b"<ix:" in prefix or b"xmlns:ix=" in prefix


def _approved_mapping_targets(
    rows: Iterable[ConceptMappingRecord],
) -> dict[tuple[str, str], IndustryFactTarget]:
    selected: dict[tuple[str, str], IndustryFactTarget] = {}
    for row in rows:
        key = (row.taxonomy, row.concept)
        if key in selected:
            continue
        selected[key] = IndustryFactTarget(
            industry_label=(
                row.scope_value if row.scope_type != MAPPING_SCOPE_COMPANY else "Company"
            ),
            raw_concept=row.concept,
            taxonomy=row.taxonomy,
            internal_metric_name=row.metric_name,
            statement_type=row.statement_type,
            required_for_core=False,
            required_for_specialized_indicators=False,
            consolidated_or_segment="consolidated",
            priority=-100,
            notes=f"Approved persisted mapping {row.mapping_id}",
        )
    return selected


def _load_approved_company_concept_profile(
    repository: ConceptMappingRepository,
    cik: str,
    industry_labels: tuple[str, ...],
) -> _ApprovedCompanyConceptProfile:
    rows = repository.list_for_company(
        cik,
        industry_labels,
        status=MAPPING_STATUS_APPROVED,
    )
    return _ApprovedCompanyConceptProfile(
        records=rows,
        mappings=_approved_mapping_targets(rows),
    )


def _deterministic_mapping_names(
    industry_labels: tuple[str, ...],
    approved_profile: _ApprovedCompanyConceptProfile,
) -> dict[tuple[str, str], str]:
    catalog_mappings = mapping_candidates_by_key(industry_labels)
    return {
        key: target.metric_name
        for key, target in {
            **catalog_mappings,
            **approved_profile.mappings,
        }.items()
    }


def _candidate_mapping_records(
    cik: str,
    candidates: Iterable[SemanticMappingCandidate],
) -> tuple[ConceptMappingRecord, ...]:
    return tuple(
        ConceptMappingRecord(
            taxonomy=candidate.taxonomy,
            concept=candidate.concept,
            namespace_uri=candidate.namespace_uri,
            metric_name=candidate.metric_name,
            statement_type=candidate.statement_type,
            scope_type=MAPPING_SCOPE_COMPANY,
            scope_value=cik,
            status=MAPPING_STATUS_CANDIDATE,
            confidence=candidate.confidence,
            match_method=candidate.match_method,
            evidence=candidate.evidence,
        )
        for candidate in candidates
    )


def _select_active_window_filings(
    recent_filings: tuple[FilingMetadata, ...],
    active_accessions: set[str],
) -> tuple[FilingMetadata, ...]:
    selected = [
        filing
        for filing in recent_filings
        if filing.accession_number in active_accessions
    ]
    if not selected:
        selected = _latest_filing_by_form(recent_filings)
    return tuple(sorted(selected, key=lambda filing: (filing.filing_date, filing.accession_number)))


def _latest_filing_by_form(filings: tuple[FilingMetadata, ...]) -> list[FilingMetadata]:
    latest: dict[str, FilingMetadata] = {}
    for filing in filings:
        if filing.form not in latest or filing.filing_date > latest[filing.form].filing_date:
            latest[filing.form] = filing
    return list(latest.values())


def _download_or_reuse_filing(
    *,
    client: SecClient,
    filing: FilingMetadata,
    base_dir: Path,
    existing_filing: FilingRecord | None,
) -> Path:
    if existing_filing is not None and existing_filing.local_path is not None and existing_filing.local_path.exists():
        return existing_filing.local_path
    return download_filing_document(client, filing, base_dir)


def _ingestion_status(existing_company: CompanyRecord | None, new_accessions: set[str]) -> str:
    if existing_company is None:
        return "initialized"
    if new_accessions:
        return "updated"
    return "checked_no_update"


def _filing_metadata_from_record(filing: FilingRecord) -> FilingMetadata:
    primary_document = _primary_document_from_record(filing)
    return FilingMetadata(
        cik=filing.accession_number.split("-", 1)[0],
        accession_number=filing.accession_number,
        form=filing.form_type,
        filing_date=filing.filing_date.isoformat(),
        primary_document=primary_document,
        document_url=filing.document_url or "",
    )


def _primary_document_from_record(filing: FilingRecord) -> str:
    if filing.local_path is not None:
        return filing.local_path.name
    if filing.document_url:
        document_name = filing.document_url.rstrip("/").rsplit("/", 1)[-1]
        if document_name:
            return document_name
    return ""


def _delete_inactive_filing_artifacts(
    *,
    base_dir: Path,
    filings: list[FilingRecord],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    base = base_dir.resolve()
    removed: list[Path] = []
    skipped: list[Path] = []
    for filing in filings:
        if filing.is_active_window or filing.local_path is None:
            continue
        resolved_path = filing.local_path.resolve()
        if not resolved_path.exists():
            continue
        if not _is_safe_delete_target(resolved_path, base):
            skipped.append(resolved_path)
            continue
        if _delete_filing_artifact_path(resolved_path):
            removed.append(resolved_path)
            removed.extend(_remove_empty_parent_dirs(resolved_path.parent, base))
        else:
            skipped.append(resolved_path)
    return tuple(dict.fromkeys(removed)), tuple(dict.fromkeys(skipped))


def delete_ingested_company(
    identifier: str,
    settings: Settings,
    *,
    delete_filings: bool = True,
) -> CompanyDeletionResult:
    """Delete all locally ingested data for one company.

    The identifier may be a ticker or a CIK, but it must exist in the local
    company registry before any rows or filing artifacts are deleted.
    """
    normalized_identifier = identifier.strip().upper()
    if not normalized_identifier:
        raise ValueError("Company identifier is required")

    cik = _cik_from_identifier(normalized_identifier)
    company_id: int | None = None
    company_found = False
    recorded_filing_paths: tuple[Path, ...] = ()

    indicator_rows_deleted = 0
    metric_rows_deleted = 0
    filing_rows_deleted = 0
    raw_fact_rows_deleted = 0
    company_rows_deleted = 0
    retrieval_chunk_rows_deleted = 0
    retrieval_state_rows_deleted = 0

    if not settings.stock_sql_db_path.exists():
        return _company_not_found_result(normalized_identifier, cik)

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        indicator_repository = FinancialIndicatorRepository(connection)
        retrieval_repository = RetrievalRepository(connection)
        raw_repository.initialize()

        company = (
            company_repository.get_by_cik(cik)
            if cik is not None
            else company_repository.get_by_ticker(normalized_identifier)
        )
        if company is not None:
            company_found = True
            cik = company.cik
            company_id = company.company_id
        else:
            return _company_not_found_result(normalized_identifier, cik)

        if company_id is None:
            raise RuntimeError(f"Stored company record for CIK {cik} did not include a company_id")

        stored_filings = filing_repository.list_filings(company_id)
        recorded_filing_paths = tuple(
            filing.local_path
            for filing in stored_filings
            if filing.local_path is not None
        )
        indicator_rows_deleted = indicator_repository.delete_by_company_id(company_id)
        metric_rows_deleted = metric_repository.delete_by_company_id(company_id)
        (
            retrieval_chunk_rows_deleted,
            retrieval_state_rows_deleted,
        ) = retrieval_repository.delete_by_company_id(company_id)
        filing_rows_deleted = filing_repository.delete_by_company_id(company_id)

        if cik is not None:
            raw_fact_rows_deleted = raw_repository.delete_by_cik(cik)
            if company_found:
                company_rows_deleted = company_repository.delete_by_cik(cik)

    filing_paths_deleted: tuple[Path, ...] = ()
    filing_paths_skipped: tuple[Path, ...] = ()
    retrieval_paths_deleted: tuple[Path, ...] = ()
    retrieval_paths_skipped: tuple[Path, ...] = ()
    if delete_filings and cik is not None:
        filing_paths_deleted, filing_paths_skipped = _delete_company_filing_artifacts(
            base_dir=settings.stock_filings_base_dir,
            cik=cik,
            recorded_paths=recorded_filing_paths,
        )
    if cik is not None:
        from src.retrieval import delete_company_retrieval_artifacts

        retrieval_paths_deleted, retrieval_paths_skipped = delete_company_retrieval_artifacts(
            settings,
            cik,
        )
    message = _company_deleted_message(
        identifier=normalized_identifier,
        cik=cik,
        filing_paths_skipped=filing_paths_skipped,
    )
    if retrieval_paths_skipped:
        message = (
            f"{message} Skipped {len(retrieval_paths_skipped)} retrieval artifact path(s)."
        )

    return CompanyDeletionResult(
        identifier=normalized_identifier,
        cik=cik,
        company_id=company_id,
        company_found=company_found,
        indicator_rows_deleted=indicator_rows_deleted,
        metric_rows_deleted=metric_rows_deleted,
        filing_rows_deleted=filing_rows_deleted,
        raw_fact_rows_deleted=raw_fact_rows_deleted,
        company_rows_deleted=company_rows_deleted,
        filing_paths_deleted=filing_paths_deleted,
        filing_paths_skipped=filing_paths_skipped,
        message=message,
        retrieval_chunk_rows_deleted=retrieval_chunk_rows_deleted,
        retrieval_state_rows_deleted=retrieval_state_rows_deleted,
        retrieval_paths_deleted=retrieval_paths_deleted,
        retrieval_paths_skipped=retrieval_paths_skipped,
    )


def _collect_quality_warnings(normalized_facts: list[NormalizedFact]) -> tuple[str, ...]:
    flags = sorted({flag for fact in normalized_facts for flag in fact.quality_flags})
    return tuple(f"Normalized facts include quality flag: {flag}" for flag in flags)


def _build_company_record(
    *,
    ticker: str,
    cik: str,
    name: str,
    submissions: dict,
    filings: tuple[FilingMetadata, ...],
    facts: list[NormalizedFact],
) -> CompanyRecord:
    latest_10k = _latest_filing(filings, "10-K")
    latest_10q = _latest_filing(filings, "10-Q")
    latest_10k_date = _filing_date(latest_10k)
    latest_10q_date = _filing_date(latest_10q)
    latest_10q_period = _period_summary_for_filing(latest_10q, facts).fiscal_period if latest_10q else None
    return CompanyRecord(
        cik=cik,
        name=name,
        ticker=ticker,
        exchange=_first_text(submissions.get("exchanges")),
        sic=_optional_text(submissions.get("sic")),
        sic_description=_optional_text(submissions.get("sicDescription")),
        latest_10k_filing_date=latest_10k_date,
        latest_10q_filing_date=latest_10q_date,
        next_check_date_10k=(
            next_check_date_for_filing("10-K", latest_10k_date)
            if latest_10k_date is not None
            else None
        ),
        next_check_date_10q=(
            next_check_date_for_filing("10-Q", latest_10q_date, latest_10q_period)
            if latest_10q_date is not None
            else None
        ),
    )


def _build_filing_records(
    *,
    company_id: int,
    filings: tuple[FilingMetadata, ...],
    downloaded_filings: tuple[Path | None, ...],
    facts: list[NormalizedFact],
    active_accessions: set[str],
) -> list[FilingRecord]:
    local_path_by_accession = {
        filing.accession_number: local_path
        for filing, local_path in zip(filings, downloaded_filings, strict=False)
    }
    records: list[FilingRecord] = []
    for filing in filings:
        summary = _period_summary_for_filing(filing, facts)
        has_source_facts = any(fact.accession_number == filing.accession_number for fact in facts)
        records.append(
            FilingRecord(
                company_id=company_id,
                accession_number=filing.accession_number,
                form_type=filing.form,
                filing_date=date.fromisoformat(filing.filing_date),
                report_date=summary.report_date,
                fiscal_year=summary.fiscal_year,
                fiscal_period=summary.fiscal_period,
                document_url=filing.document_url,
                local_path=local_path_by_accession.get(filing.accession_number),
                is_active_window=filing.accession_number in active_accessions or not has_source_facts,
            )
        )
    return records


def _build_financial_metrics(
    *,
    company_id: int,
    base_metrics: list[BaseMetricRecord],
    filing_id_by_accession: dict[str, int],
) -> list[FinancialMetric]:
    return [
        FinancialMetric(
            company_id=company_id,
            filing_id=filing_id_by_accession.get(metric.accession_number),
            accession_number=metric.accession_number,
            raw_fact_id=metric.raw_fact_id,
            statement_type=metric.statement_type,
            metric_name=metric.metric_name,
            value_numeric=metric.value_numeric,
            value_raw=metric.value_raw,
            unit=metric.unit,
            period_type=metric.period_type,
            fiscal_year=metric.fiscal_year,
            fiscal_period=metric.fiscal_period,
            start_date=metric.start_date,
            end_date=metric.end_date,
            filing_date=metric.filing_date,
            is_active_window=metric.is_active_window,
        )
        for metric in base_metrics
    ]


def _period_summary_for_filing(
    filing: FilingMetadata,
    facts: list[NormalizedFact],
) -> _FilingPeriodSummary:
    candidates = [
        fact
        for fact in facts
        if fact.accession_number == filing.accession_number
        and fact.form == filing.form
        and fact.fiscal_year is not None
        and fact.fiscal_period is not None
    ]
    if not candidates:
        return _FilingPeriodSummary(fiscal_year=None, fiscal_period=None, report_date=None)

    best = max(
        candidates,
        key=lambda fact: (
            fact.fiscal_year or 0,
            PERIOD_ORDER.get((fact.fiscal_period or "").upper(), 0),
            fact.end_date or date.min,
        ),
    )
    report_dates = [
        fact.end_date
        for fact in candidates
        if fact.fiscal_year == best.fiscal_year and fact.fiscal_period == best.fiscal_period and fact.end_date is not None
    ]
    return _FilingPeriodSummary(
        fiscal_year=best.fiscal_year,
        fiscal_period=best.fiscal_period,
        report_date=max(report_dates) if report_dates else best.end_date,
    )


def _latest_filing(filings: tuple[FilingMetadata, ...], form: str) -> FilingMetadata | None:
    matching = [filing for filing in filings if filing.form == form]
    if not matching:
        return None
    return max(matching, key=lambda filing: filing.filing_date)


def _filing_date(filing: FilingMetadata | None) -> date | None:
    return date.fromisoformat(filing.filing_date) if filing is not None else None


def _company_name(companyfacts: dict, submissions: dict, fallback: str) -> str:
    return (
        _optional_text(companyfacts.get("entityName"))
        or _optional_text(submissions.get("name"))
        or fallback.strip()
    )


def _first_text(value: object) -> str | None:
    if isinstance(value, list):
        if not value:
            return None
        return _optional_text(value[0])
    return _optional_text(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cik_from_identifier(identifier: str) -> str | None:
    text = identifier.strip()
    if not text.isdigit():
        return None
    if len(text) > 10:
        raise ValueError(f"CIK is longer than 10 digits: {text}")
    return text.zfill(10)


def _company_not_found_result(identifier: str, cik: str | None) -> CompanyDeletionResult:
    message = f"No ingested company found for identifier '{identifier}'."
    if cik is not None and cik != identifier:
        message = f"No ingested company found for identifier '{identifier}' (CIK {cik})."
    return CompanyDeletionResult(
        identifier=identifier,
        cik=cik,
        company_id=None,
        company_found=False,
        indicator_rows_deleted=0,
        metric_rows_deleted=0,
        filing_rows_deleted=0,
        raw_fact_rows_deleted=0,
        company_rows_deleted=0,
        message=message,
    )


def _company_deleted_message(
    *,
    identifier: str,
    cik: str | None,
    filing_paths_skipped: tuple[Path, ...],
) -> str:
    company_label = f"identifier '{identifier}'"
    if cik is not None:
        company_label = f"{company_label} (CIK {cik})"
    if filing_paths_skipped:
        return (
            f"Deleted ingested company for {company_label}, "
            "but some filing artifacts could not be removed."
        )
    return f"Deleted ingested company for {company_label}."


def _delete_company_filing_artifacts(
    *,
    base_dir: Path,
    cik: str,
    recorded_paths: tuple[Path, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    removed: list[Path] = []
    skipped: list[Path] = []
    base = base_dir.resolve()

    company_dir = (base_dir / cik).resolve()
    if company_dir.exists():
        if _is_safe_delete_target(company_dir, base):
            if _delete_filing_artifact_path(company_dir):
                removed.append(company_dir)
            else:
                skipped.append(company_dir)
        else:
            skipped.append(company_dir)

    for path in recorded_paths:
        resolved_path = path.resolve()
        if not resolved_path.exists():
            continue
        if not _is_safe_delete_target(resolved_path, base):
            skipped.append(resolved_path)
            continue
        if _delete_filing_artifact_path(resolved_path):
            removed.append(resolved_path)
            removed.extend(_remove_empty_parent_dirs(resolved_path.parent, base))
        else:
            skipped.append(resolved_path)

    return tuple(dict.fromkeys(removed)), tuple(dict.fromkeys(skipped))


def _delete_filing_artifact_path(path: Path) -> bool:
    try:
        if path.is_dir():
            shutil.rmtree(path, onerror=_make_writable_and_retry)
        else:
            _unlink_file(path)
    except OSError:
        return False
    return True


def _unlink_file(path: Path) -> None:
    try:
        path.unlink()
    except PermissionError:
        _make_writable(path)
        path.unlink()


def _make_writable_and_retry(
    function: Callable[[str], object],
    path: str,
    exc_info: tuple[type[BaseException], BaseException, object],
) -> None:
    if not issubclass(exc_info[0], PermissionError):
        raise exc_info[1]

    _make_writable(Path(path))
    function(path)


def _make_writable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IWRITE)


def _remove_empty_parent_dirs(start: Path, stop: Path) -> list[Path]:
    removed: list[Path] = []
    current = start.resolve()
    while current != stop and _is_child_path(current, stop):
        try:
            current.rmdir()
        except OSError:
            break
        removed.append(current)
        current = current.parent
    return removed


def _is_safe_delete_target(path: Path, base: Path) -> bool:
    resolved_path = path.resolve()
    resolved_base = base.resolve()
    return resolved_path != resolved_base and _is_child_path(resolved_path, resolved_base)


def _is_child_path(path: Path, base: Path) -> bool:
    return base == path or base in path.parents
