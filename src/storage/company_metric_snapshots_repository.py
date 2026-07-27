"""SQLite persistence for immutable published company metric snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal

from src.storage.database import initialize_database
from src.storage.metrics_repository import FinancialMetric

SNAPSHOT_STATUS_PUBLISHED = "published"
SNAPSHOT_TARGET_STATUS_MAPPED = "mapped"
SNAPSHOT_TARGET_STATUS_RECOVERED = "recovered"


@dataclass(frozen=True)
class SnapshotTargetKey:
    """Identity shared by a current metric and its publication status."""

    statement_type: str
    metric_name: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None


@dataclass(frozen=True)
class SnapshotTargetStatus:
    """Publication status for one target in one fiscal period."""

    statement_type: str
    metric_name: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    status: str
    failure_reason: str | None = None

    @property
    def target_key(self) -> SnapshotTargetKey:
        """Return the target identity governed by this status."""
        return SnapshotTargetKey(
            statement_type=self.statement_type,
            metric_name=self.metric_name,
            period_type=self.period_type,
            fiscal_year=self.fiscal_year,
            fiscal_period=self.fiscal_period,
        )


@dataclass(frozen=True)
class SnapshotComponentVersion:
    """Version of one processor, model, prompt, or evidence contract."""

    component: str
    version: str


@dataclass(frozen=True)
class PublishedCompanyMetricSnapshot:
    """One immutable, consumer-visible company metric state."""

    company_metric_snapshot_id: int
    company_id: int
    snapshot_version: int
    status: str
    completed_at: datetime
    published_at: datetime
    raw_fact_ids: tuple[int, ...]
    metrics: tuple[FinancialMetric, ...]
    target_statuses: tuple[SnapshotTargetStatus, ...]
    component_versions: tuple[SnapshotComponentVersion, ...]


@dataclass(frozen=True)
class MetricInvalidation:
    """One current metric removed or replaced during publication."""

    metric: FinancialMetric
    reason: str


@dataclass(frozen=True)
class ArchivedFinancialMetric:
    """Immutable audit evidence for one invalidated current metric."""

    company_metric_snapshot_audit_id: int
    company_id: int
    invalidated_by_company_metric_snapshot_id: int
    metric: FinancialMetric
    reason: str
    archived_at: datetime


class CompanyMetricSnapshotRepository:
    """Persist and retrieve immutable company metric snapshots."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required snapshot tables."""
        initialize_database(self.connection)

    def next_version(self, company_id: int) -> int:
        """Return the next monotonic snapshot version for a company."""
        row = self.connection.execute(
            """
            SELECT COALESCE(MAX(snapshot_version), 0) + 1 AS next_version
            FROM company_metric_snapshots
            WHERE company_id = ?
            """,
            [company_id],
        ).fetchone()
        return int(row["next_version"])

    def insert_published(
        self,
        *,
        company_id: int,
        snapshot_version: int,
        completed_at: datetime,
        published_at: datetime,
        raw_fact_ids: tuple[int, ...],
        metrics: tuple[FinancialMetric, ...],
        target_statuses: tuple[SnapshotTargetStatus, ...],
        component_versions: tuple[SnapshotComponentVersion, ...],
    ) -> PublishedCompanyMetricSnapshot:
        """Insert one immutable published snapshot without committing."""
        cursor = self.connection.execute(
            """
            INSERT INTO company_metric_snapshots (
                company_id,
                snapshot_version,
                status,
                completed_at,
                published_at,
                raw_fact_ids_json,
                metric_records_json,
                target_statuses_json,
                component_versions_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                snapshot_version,
                SNAPSHOT_STATUS_PUBLISHED,
                completed_at.isoformat(),
                published_at.isoformat(),
                json.dumps(raw_fact_ids),
                _metrics_to_json(metrics),
                json.dumps(
                    [asdict(status) for status in target_statuses],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    [asdict(version) for version in component_versions],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        snapshot_id = cursor.lastrowid
        if snapshot_id is None:
            raise RuntimeError("Snapshot insert returned no identifier")
        return PublishedCompanyMetricSnapshot(
            company_metric_snapshot_id=int(snapshot_id),
            company_id=company_id,
            snapshot_version=snapshot_version,
            status=SNAPSHOT_STATUS_PUBLISHED,
            completed_at=completed_at,
            published_at=published_at,
            raw_fact_ids=raw_fact_ids,
            metrics=metrics,
            target_statuses=target_statuses,
            component_versions=component_versions,
        )

    def set_current(
        self,
        snapshot: PublishedCompanyMetricSnapshot,
    ) -> None:
        """Point consumers at a published snapshot without committing."""
        self.connection.execute(
            """
            INSERT INTO company_current_metric_snapshots (
                company_id,
                company_metric_snapshot_id,
                updated_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                company_metric_snapshot_id =
                    excluded.company_metric_snapshot_id,
                updated_at = excluded.updated_at
            """,
            (
                snapshot.company_id,
                snapshot.company_metric_snapshot_id,
                snapshot.published_at.isoformat(),
            ),
        )

    def archive_invalidated_metrics(
        self,
        *,
        invalidations: tuple[MetricInvalidation, ...],
        invalidated_by: PublishedCompanyMetricSnapshot,
        archived_at: datetime,
    ) -> None:
        """Archive invalidated current metrics without committing."""
        rows = []
        for invalidation in invalidations:
            metric = invalidation.metric
            if metric.metric_id is None:
                raise ValueError(
                    "invalidated metric requires a stored metric_id"
                )
            rows.append(
                (
                    invalidated_by.company_id,
                    invalidated_by.company_metric_snapshot_id,
                    metric.metric_id,
                    json.dumps(
                        _metric_to_dict(metric),
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                    invalidation.reason,
                    archived_at.isoformat(),
                )
            )
        if rows:
            self.connection.executemany(
                """
                INSERT INTO company_metric_snapshot_audit_records (
                    company_id,
                    invalidated_by_company_metric_snapshot_id,
                    source_metric_id,
                    metric_record_json,
                    reason,
                    archived_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_current(
        self,
        company_id: int,
    ) -> PublishedCompanyMetricSnapshot | None:
        """Return the one consumer-visible snapshot for a company."""
        row = self.connection.execute(
            """
            SELECT snapshots.*
            FROM company_current_metric_snapshots AS current
            JOIN company_metric_snapshots AS snapshots
              ON snapshots.company_metric_snapshot_id =
                 current.company_metric_snapshot_id
            WHERE current.company_id = ?
            """,
            [company_id],
        ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def list_history(
        self,
        company_id: int,
    ) -> tuple[PublishedCompanyMetricSnapshot, ...]:
        """Return immutable snapshots in ascending version order."""
        rows = self.connection.execute(
            """
            SELECT *
            FROM company_metric_snapshots
            WHERE company_id = ?
            ORDER BY snapshot_version
            """,
            [company_id],
        ).fetchall()
        return tuple(_row_to_snapshot(row) for row in rows)

    def list_metric_audit(
        self,
        company_id: int,
    ) -> tuple[ArchivedFinancialMetric, ...]:
        """Return invalidated metric audit records in publication order."""
        rows = self.connection.execute(
            """
            SELECT *
            FROM company_metric_snapshot_audit_records
            WHERE company_id = ?
            ORDER BY company_metric_snapshot_audit_id
            """,
            [company_id],
        ).fetchall()
        return tuple(
            ArchivedFinancialMetric(
                company_metric_snapshot_audit_id=row[
                    "company_metric_snapshot_audit_id"
                ],
                company_id=row["company_id"],
                invalidated_by_company_metric_snapshot_id=row[
                    "invalidated_by_company_metric_snapshot_id"
                ],
                metric=_dict_to_metric(
                    json.loads(row["metric_record_json"])
                ),
                reason=row["reason"],
                archived_at=datetime.fromisoformat(row["archived_at"]),
            )
            for row in rows
        )


def _metrics_to_json(metrics: tuple[FinancialMetric, ...]) -> str:
    return json.dumps(
        [_metric_to_dict(metric) for metric in metrics],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _metric_to_dict(metric: FinancialMetric) -> dict[str, object]:
    return {
        "company_id": metric.company_id,
        "accession_number": metric.accession_number,
        "statement_type": metric.statement_type,
        "metric_name": metric.metric_name,
        "unit": metric.unit,
        "period_type": metric.period_type,
        "metric_id": metric.metric_id,
        "filing_id": metric.filing_id,
        "raw_fact_id": metric.raw_fact_id,
        "origin": metric.origin,
        "recovery_application_id": metric.recovery_application_id,
        "value_numeric": (
            str(metric.value_numeric)
            if metric.value_numeric is not None
            else None
        ),
        "value_raw": metric.value_raw,
        "fiscal_year": metric.fiscal_year,
        "fiscal_period": metric.fiscal_period,
        "start_date": _date_to_text(metric.start_date),
        "end_date": _date_to_text(metric.end_date),
        "filing_date": _date_to_text(metric.filing_date),
        "is_active_window": metric.is_active_window,
        "created_at": metric.created_at,
    }


def _row_to_snapshot(row: sqlite3.Row) -> PublishedCompanyMetricSnapshot:
    return PublishedCompanyMetricSnapshot(
        company_metric_snapshot_id=row["company_metric_snapshot_id"],
        company_id=row["company_id"],
        snapshot_version=row["snapshot_version"],
        status=row["status"],
        completed_at=datetime.fromisoformat(row["completed_at"]),
        published_at=datetime.fromisoformat(row["published_at"]),
        raw_fact_ids=tuple(json.loads(row["raw_fact_ids_json"])),
        metrics=tuple(
            _dict_to_metric(metric)
            for metric in json.loads(row["metric_records_json"])
        ),
        target_statuses=tuple(
            SnapshotTargetStatus(**status)
            for status in json.loads(row["target_statuses_json"])
        ),
        component_versions=tuple(
            SnapshotComponentVersion(**version)
            for version in json.loads(row["component_versions_json"])
        ),
    )


def _dict_to_metric(payload: dict[str, object]) -> FinancialMetric:
    numeric = payload["value_numeric"]
    return FinancialMetric(
        company_id=int(payload["company_id"]),
        accession_number=str(payload["accession_number"]),
        statement_type=str(payload["statement_type"]),
        metric_name=str(payload["metric_name"]),
        unit=str(payload["unit"]),
        period_type=str(payload["period_type"]),
        metric_id=_optional_int(payload["metric_id"]),
        filing_id=_optional_int(payload["filing_id"]),
        raw_fact_id=_optional_int(payload["raw_fact_id"]),
        origin=str(payload["origin"]),
        recovery_application_id=_optional_int(
            payload["recovery_application_id"]
        ),
        value_numeric=Decimal(str(numeric)) if numeric is not None else None,
        value_raw=payload["value_raw"],
        fiscal_year=_optional_int(payload["fiscal_year"]),
        fiscal_period=_optional_text(payload["fiscal_period"]),
        start_date=_text_to_date(payload["start_date"]),
        end_date=_text_to_date(payload["end_date"]),
        filing_date=_text_to_date(payload["filing_date"]),
        is_active_window=bool(payload["is_active_window"]),
        created_at=_optional_text(payload["created_at"]),
    )


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None
