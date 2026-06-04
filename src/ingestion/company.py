"""Company-level ingestion orchestration."""

from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from src.ingestion.companyfacts import get_companyfacts
from src.ingestion.filings import FilingMetadata, require_latest_filings, download_filing_document
from src.ingestion.refresh_policy import next_check_date_for_filing
from src.ingestion.sec_client import SecClient
from src.ingestion.submissions import get_company_submissions
from src.ingestion.tickers import load_ticker_mapping, resolve_ticker_to_cik
from src.processing import (
    BaseMetricRecord,
    NormalizedFact,
    active_accessions_for_facts,
    active_period_keys,
    map_raw_facts_to_base_metrics,
    normalize_companyfacts,
)
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FilingRecord,
    FilingRepository,
    FinancialMetric,
    FinancialMetricRepository,
    RawFactRepository,
    connect_sqlite,
)

if TYPE_CHECKING:
    from src.config import Settings

PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class CompanyIngestionResult:
    """Result summary for one company ingestion run."""

    ticker: str
    cik: str
    filings: tuple[FilingMetadata, ...]
    downloaded_filings: tuple[Path, ...]
    normalized_fact_count: int
    stored_fact_count: int
    warnings: tuple[str, ...] = ()
    company_id: int | None = None
    stored_filing_count: int = 0
    stored_metric_count: int = 0
    active_metric_count: int = 0


@dataclass(frozen=True)
class CompanyDeletionResult:
    """Summary of deleted local data for one ingested company."""

    identifier: str
    cik: str | None
    company_id: int | None
    company_found: bool
    metric_rows_deleted: int
    filing_rows_deleted: int
    raw_fact_rows_deleted: int
    company_rows_deleted: int
    filing_paths_deleted: tuple[Path, ...] = ()
    filing_paths_skipped: tuple[Path, ...] = ()
    message: str | None = None


@dataclass(frozen=True)
class _FilingPeriodSummary:
    fiscal_year: int | None
    fiscal_period: str | None
    report_date: date | None


def ingest_company(ticker: str, settings: Settings) -> CompanyIngestionResult:
    """Ingest one company from SEC data into local storage."""
    client = SecClient(settings.sec_user_agent)

    ticker_mapping = load_ticker_mapping(client)
    normalized_ticker = ticker.strip().upper()
    cik = resolve_ticker_to_cik(normalized_ticker, ticker_mapping)
    ticker_entry = ticker_mapping[normalized_ticker]

    submissions = get_company_submissions(client, cik)
    companyfacts = get_companyfacts(client, cik)

    filings = tuple(require_latest_filings(submissions, {"10-K", "10-Q"}))
    downloaded_filings = tuple(
        download_filing_document(client, filing, settings.stock_filings_base_dir)
        for filing in filings
    )

    normalized_facts = normalize_companyfacts(companyfacts)
    warnings = _collect_quality_warnings(normalized_facts)

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)

        raw_repository.initialize()
        stored_fact_count = raw_repository.upsert_facts(normalized_facts)
        stored_fact_records = raw_repository.list_fact_records(cik)
        stored_facts = [record.fact for record in stored_fact_records]
        active_keys = active_period_keys(stored_facts)
        active_accessions = active_accessions_for_facts(stored_facts, active_keys)

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
        filing_id_by_accession = {
            filing.accession_number: filing.filing_id
            for filing in stored_filings
            if filing.filing_id is not None
        }

        base_metrics = map_raw_facts_to_base_metrics(
            ((record.raw_fact_id, record.fact) for record in stored_fact_records),
            active_keys,
        )
        financial_metrics = _build_financial_metrics(
            company_id=company.company_id,
            base_metrics=base_metrics,
            filing_id_by_accession=filing_id_by_accession,
        )
        stored_metric_count = metric_repository.upsert_metrics(financial_metrics)
        active_metric_count = len(metric_repository.list_metrics(company.company_id))

    return CompanyIngestionResult(
        ticker=normalized_ticker,
        cik=cik,
        filings=filings,
        downloaded_filings=downloaded_filings,
        normalized_fact_count=len(normalized_facts),
        stored_fact_count=stored_fact_count,
        warnings=warnings,
        company_id=company.company_id,
        stored_filing_count=stored_filing_count,
        stored_metric_count=stored_metric_count,
        active_metric_count=active_metric_count,
    )


def delete_ingested_company(
    identifier: str,
    settings: Settings,
    *,
    delete_filings: bool = True,
) -> CompanyDeletionResult:
    """Delete all locally ingested data for one company.

    The identifier may be a ticker that exists in the local company registry or
    a CIK. This function does not contact SEC; if a ticker is not present in
    the local registry, there is no local source for resolving it to a CIK.
    """
    normalized_identifier = identifier.strip().upper()
    if not normalized_identifier:
        raise ValueError("Company identifier is required")

    cik = _cik_from_identifier(normalized_identifier)
    company_id: int | None = None
    company_found = False
    recorded_filing_paths: tuple[Path, ...] = ()

    metric_rows_deleted = 0
    filing_rows_deleted = 0
    raw_fact_rows_deleted = 0
    company_rows_deleted = 0
    message: str | None = None

    if not settings.stock_sql_db_path.exists():
        return _company_not_found_result(normalized_identifier, cik)

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
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
        elif cik is None:
            return _company_not_found_result(normalized_identifier, cik)

        if company_id is not None:
            stored_filings = filing_repository.list_filings(company_id)
            recorded_filing_paths = tuple(
                filing.local_path
                for filing in stored_filings
                if filing.local_path is not None
            )
            metric_rows_deleted = metric_repository.delete_by_company_id(company_id)
            filing_rows_deleted = filing_repository.delete_by_company_id(company_id)
        elif cik is not None and not _has_orphan_company_data(
            raw_repository=raw_repository,
            filings_base_dir=settings.stock_filings_base_dir,
            cik=cik,
        ):
            return _company_not_found_result(normalized_identifier, cik)
        else:
            message = f"No company registry row found for CIK {cik}; deleted orphan local data."

        if cik is not None:
            raw_fact_rows_deleted = raw_repository.delete_by_cik(cik)
            if company_found:
                company_rows_deleted = company_repository.delete_by_cik(cik)

    filing_paths_deleted: tuple[Path, ...] = ()
    filing_paths_skipped: tuple[Path, ...] = ()
    if delete_filings and cik is not None:
        filing_paths_deleted, filing_paths_skipped = _delete_company_filing_artifacts(
            base_dir=settings.stock_filings_base_dir,
            cik=cik,
            recorded_paths=recorded_filing_paths,
        )

    return CompanyDeletionResult(
        identifier=normalized_identifier,
        cik=cik,
        company_id=company_id,
        company_found=company_found,
        metric_rows_deleted=metric_rows_deleted,
        filing_rows_deleted=filing_rows_deleted,
        raw_fact_rows_deleted=raw_fact_rows_deleted,
        company_rows_deleted=company_rows_deleted,
        filing_paths_deleted=filing_paths_deleted,
        filing_paths_skipped=filing_paths_skipped,
        message=message,
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
    downloaded_filings: tuple[Path, ...],
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
        metric_rows_deleted=0,
        filing_rows_deleted=0,
        raw_fact_rows_deleted=0,
        company_rows_deleted=0,
        message=message,
    )


def _has_orphan_company_data(
    *,
    raw_repository: RawFactRepository,
    filings_base_dir: Path,
    cik: str,
) -> bool:
    company_dir = (filings_base_dir / cik).resolve()
    base_dir = filings_base_dir.resolve()
    return bool(raw_repository.list_fact_records(cik)) or (
        company_dir.exists() and _is_safe_delete_target(company_dir, base_dir)
    )


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
