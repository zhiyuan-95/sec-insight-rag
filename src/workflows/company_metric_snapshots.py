"""Atomic publication workflow for current company metric snapshots."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from src.processing.company_identity import same_cik
from src.storage.company_metric_snapshots_repository import (
    CompanyMetricSnapshotRepository,
    MetricInvalidation,
    PublishedCompanyMetricSnapshot,
    SnapshotComponentVersion,
    SnapshotTargetKey,
    SnapshotTargetStatus,
    SNAPSHOT_TARGET_STATUS_MAPPED,
    SNAPSHOT_TARGET_STATUS_RECOVERED,
)
from src.storage.company_repository import CompanyRepository
from src.storage.facts_repository import RawFactRepository, StoredRawFact
from src.storage.metrics_repository import (
    METRIC_ORIGIN_REPORTED_MAPPING,
    FinancialMetric,
    FinancialMetricRepository,
)
from src.storage.recovery_applications_repository import (
    RecoveryApplicationRepository,
)


@dataclass(frozen=True)
class StagedCompanyMetricSnapshot:
    """Completed MS2/MS3 results awaiting one atomic publication."""

    company_id: int
    raw_fact_ids: tuple[int, ...]
    metrics: tuple[FinancialMetric, ...]
    target_statuses: tuple[SnapshotTargetStatus, ...]
    component_versions: tuple[SnapshotComponentVersion, ...]
    completed_at: datetime


def publish_company_metric_snapshot(
    *,
    stage: StagedCompanyMetricSnapshot,
    connection: sqlite3.Connection,
) -> PublishedCompanyMetricSnapshot:
    """Replace current company metrics and publish one version atomically."""
    if connection.in_transaction:
        raise ValueError("snapshot publication requires transaction ownership")
    snapshot_repository = CompanyMetricSnapshotRepository(connection)
    metric_repository = FinancialMetricRepository(connection)
    snapshot_repository.initialize()
    company = CompanyRepository(connection).get_by_id(stage.company_id)
    if company is None:
        raise ValueError("snapshot company does not exist")
    if not stage.component_versions:
        raise ValueError("snapshot requires component versions")
    if any(
        not version.component.strip() or not version.version.strip()
        for version in stage.component_versions
    ):
        raise ValueError(
            "snapshot component version requires nonblank values"
        )
    if len(
        {
            version.component
            for version in stage.component_versions
        }
    ) != len(stage.component_versions):
        raise ValueError("duplicate snapshot component version")
    if any(
        not status.statement_type.strip()
        or not status.metric_name.strip()
        or not status.period_type.strip()
        or not status.status.strip()
        for status in stage.target_statuses
    ):
        raise ValueError(
            "snapshot target status requires nonblank identity and status"
        )
    if len(
        {
            status.target_key
            for status in stage.target_statuses
        }
    ) != len(stage.target_statuses):
        raise ValueError("duplicate snapshot target status")
    if len(
        {
            _metric_target_key(metric)
            for metric in stage.metrics
        }
    ) != len(stage.metrics):
        raise ValueError("duplicate snapshot current metric target")
    if any(metric.company_id != stage.company_id for metric in stage.metrics):
        raise ValueError("snapshot metric company does not match stage company")
    _validate_target_status_outcomes(
        metrics=stage.metrics,
        target_statuses=stage.target_statuses,
    )
    _validate_current_metric_statuses(
        metrics=stage.metrics,
        target_statuses=stage.target_statuses,
    )
    raw_fact_ids = tuple(sorted(set(stage.raw_fact_ids)))
    published_at = datetime.now(timezone.utc)

    try:
        connection.execute("BEGIN IMMEDIATE")
        raw_facts_by_id = _validate_raw_fact_ownership(
            repository=RawFactRepository(connection),
            company_cik=company.cik,
            raw_fact_ids=raw_fact_ids,
        )
        _validate_direct_metric_evidence(
            metrics=stage.metrics,
            raw_facts_by_id=raw_facts_by_id,
        )
        _validate_recovered_metric_evidence(
            metrics=stage.metrics,
            raw_fact_ids=raw_fact_ids,
            application_repository=RecoveryApplicationRepository(connection),
        )
        snapshot_version = snapshot_repository.next_version(
            stage.company_id
        )
        current_metrics = tuple(
            metric_repository.list_metrics(
                stage.company_id,
                active_only=False,
            )
        )
        _validate_stale_metric_failures(
            current_metrics=current_metrics,
            staged_metrics=stage.metrics,
            target_statuses=stage.target_statuses,
        )
        invalidations = _metric_invalidations(
            current_metrics=current_metrics,
            staged_metrics=stage.metrics,
            target_statuses=stage.target_statuses,
        )
        metric_repository.delete_by_company_id(
            stage.company_id,
            commit=False,
        )
        metric_repository.upsert_metrics(
            list(stage.metrics),
            commit=False,
        )
        stored_metrics = tuple(
            metric_repository.list_metrics(
                stage.company_id,
                active_only=False,
            )
        )
        published = snapshot_repository.insert_published(
            company_id=stage.company_id,
            snapshot_version=snapshot_version,
            completed_at=stage.completed_at,
            published_at=published_at,
            raw_fact_ids=raw_fact_ids,
            metrics=stored_metrics,
            target_statuses=stage.target_statuses,
            component_versions=stage.component_versions,
        )
        snapshot_repository.archive_invalidated_metrics(
            invalidations=invalidations,
            invalidated_by=published,
            archived_at=published_at,
        )
        snapshot_repository.set_current(published)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return published


def _validate_raw_fact_ownership(
    *,
    repository: RawFactRepository,
    company_cik: str,
    raw_fact_ids: tuple[int, ...],
) -> dict[int, StoredRawFact]:
    records = repository.get_by_ids(raw_fact_ids)
    if (
        len(records) != len(raw_fact_ids)
        or any(
            not same_cik(record.fact.cik, company_cik)
            for record in records
        )
    ):
        raise ValueError("snapshot raw facts do not belong to stage company")
    return {
        record.raw_fact_id: record
        for record in records
    }


def _validate_direct_metric_evidence(
    *,
    metrics: tuple[FinancialMetric, ...],
    raw_facts_by_id: dict[int, StoredRawFact],
) -> None:
    for metric in metrics:
        if metric.origin != METRIC_ORIGIN_REPORTED_MAPPING:
            continue
        if metric.raw_fact_id is None:
            # The metric repository remains the final provenance validator.
            # Keeping this check there also exercises transaction rollback
            # after publication has begun replacing the current metric set.
            continue
        if metric.raw_fact_id not in raw_facts_by_id:
            raise ValueError("direct metric raw fact is not staged")
        fact = raw_facts_by_id[metric.raw_fact_id].fact
        if (
            metric.accession_number != fact.accession_number
            or metric.value_numeric != fact.value
            or metric.value_raw != fact.value_raw
            or metric.unit != fact.unit
            or metric.period_type != fact.period_type
            or metric.fiscal_year != fact.fiscal_year
            or metric.fiscal_period != fact.fiscal_period
            or metric.start_date != fact.start_date
            or metric.end_date != fact.end_date
            or metric.filing_date != fact.filed_date
        ):
            raise ValueError(
                "direct metric does not match staged raw fact"
            )


def _validate_stale_metric_failures(
    *,
    current_metrics: tuple[FinancialMetric, ...],
    staged_metrics: tuple[FinancialMetric, ...],
    target_statuses: tuple[SnapshotTargetStatus, ...],
) -> None:
    staged_targets = {
        _metric_target_key(metric)
        for metric in staged_metrics
    }
    failed_targets = {
        status.target_key
        for status in target_statuses
        if status.failure_reason
    }
    if any(
        _metric_target_key(metric) not in staged_targets
        and _metric_target_key(metric) not in failed_targets
        for metric in current_metrics
    ):
        raise ValueError("stale metric requires target failure status")


def _validate_current_metric_statuses(
    *,
    metrics: tuple[FinancialMetric, ...],
    target_statuses: tuple[SnapshotTargetStatus, ...],
) -> None:
    status_by_target = {
        status.target_key: status
        for status in target_statuses
    }
    for metric in metrics:
        status = status_by_target.get(_metric_target_key(metric))
        if status is None:
            raise ValueError("current metric requires target status")
        expected_status = (
            SNAPSHOT_TARGET_STATUS_MAPPED
            if metric.origin == METRIC_ORIGIN_REPORTED_MAPPING
            else SNAPSHOT_TARGET_STATUS_RECOVERED
        )
        if (
            status.status != expected_status
            or status.failure_reason is not None
        ):
            raise ValueError(
                "current metric requires successful target status"
            )


def _validate_target_status_outcomes(
    *,
    metrics: tuple[FinancialMetric, ...],
    target_statuses: tuple[SnapshotTargetStatus, ...],
) -> None:
    current_targets = {
        _metric_target_key(metric)
        for metric in metrics
    }
    successful_statuses = {
        SNAPSHOT_TARGET_STATUS_MAPPED,
        SNAPSHOT_TARGET_STATUS_RECOVERED,
    }
    for status in target_statuses:
        if status.status in successful_statuses:
            if (
                status.target_key not in current_targets
                or status.failure_reason is not None
            ):
                raise ValueError(
                    "successful target status requires current metric"
                )
            continue
        if (
            status.failure_reason is None
            or not status.failure_reason.strip()
        ):
            raise ValueError(
                "failed target status requires failure reason"
            )


def _validate_recovered_metric_evidence(
    *,
    metrics: tuple[FinancialMetric, ...],
    raw_fact_ids: tuple[int, ...],
    application_repository: RecoveryApplicationRepository,
) -> None:
    staged_raw_fact_ids = set(raw_fact_ids)
    for metric in metrics:
        if metric.recovery_application_id is None:
            continue
        stored = application_repository.get_by_id(
            metric.recovery_application_id
        )
        if (
            stored is None
            or not set(stored.application.source_raw_fact_ids).issubset(
                staged_raw_fact_ids
            )
        ):
            raise ValueError(
                "recovered metric source facts are not staged"
            )


def _metric_invalidations(
    *,
    current_metrics: tuple[FinancialMetric, ...],
    staged_metrics: tuple[FinancialMetric, ...],
    target_statuses: tuple[SnapshotTargetStatus, ...],
) -> tuple[MetricInvalidation, ...]:
    failure_reason_by_target = {
        status.target_key: status.failure_reason
        for status in target_statuses
        if status.failure_reason
    }
    staged_targets = {
        _metric_target_key(metric)
        for metric in staged_metrics
    }
    invalidations: list[MetricInvalidation] = []
    for metric in current_metrics:
        if any(
            _same_metric_record(metric, staged)
            for staged in staged_metrics
        ):
            continue
        target_key = _metric_target_key(metric)
        reason = (
            failure_reason_by_target.get(target_key)
            if target_key not in staged_targets
            else "replaced_by_new_current_metric"
        )
        if reason is None:
            raise ValueError("stale metric requires target failure status")
        invalidations.append(
            MetricInvalidation(metric=metric, reason=reason)
        )
    return tuple(invalidations)


def _same_metric_record(
    left: FinancialMetric,
    right: FinancialMetric,
) -> bool:
    return replace(left, metric_id=None, created_at=None) == replace(
        right,
        metric_id=None,
        created_at=None,
    )


def _metric_target_key(
    metric: FinancialMetric,
) -> SnapshotTargetKey:
    return SnapshotTargetKey(
        statement_type=metric.statement_type,
        metric_name=metric.metric_name,
        period_type=metric.period_type,
        fiscal_year=metric.fiscal_year,
        fiscal_period=metric.fiscal_period,
    )
