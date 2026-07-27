"""SQLite repository for base financial metrics mapped from raw XBRL facts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.processing.company_identity import same_cik
from src.processing.recovery_applications import (
    RECOVERY_APPLICATION_SUCCEEDED,
    recovery_application_from_json,
    recovery_metric_source_accession,
)
from src.storage.database import initialize_database

METRIC_ORIGIN_REPORTED_MAPPING = "reported_mapping"
METRIC_ORIGIN_FORMULA_RECOVERY = "formula_recovery"
METRIC_ORIGIN_AFFIRMATIVE_ZERO_RECOVERY = "affirmative_zero_recovery"
_RECOVERY_ORIGINS = {
    METRIC_ORIGIN_FORMULA_RECOVERY,
    METRIC_ORIGIN_AFFIRMATIVE_ZERO_RECOVERY,
}


@dataclass(frozen=True)
class FinancialMetric:
    """A business-friendly base metric with source traceability."""

    company_id: int
    accession_number: str
    statement_type: str
    metric_name: str
    unit: str
    period_type: str
    metric_id: int | None = None
    filing_id: int | None = None
    raw_fact_id: int | None = None
    origin: str = METRIC_ORIGIN_REPORTED_MAPPING
    recovery_application_id: int | None = None
    value_numeric: Decimal | None = None
    value_raw: object = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    filing_date: date | None = None
    is_active_window: bool = True
    created_at: str | None = None


class FinancialMetricRepository:
    """Persist and retrieve base financial metrics."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)

    def upsert_metrics(
        self,
        metrics: list[FinancialMetric],
        *,
        commit: bool = True,
    ) -> int:
        """Insert or update base metrics by source fact identity."""
        if not metrics:
            return 0
        for metric in metrics:
            _validate_metric_provenance(metric, self.connection)
        now = datetime.now(timezone.utc).isoformat()
        direct_rows = [
            _metric_to_row(metric, now)
            for metric in metrics
            if metric.origin not in _RECOVERY_ORIGINS
        ]
        recovered_rows = [
            _metric_to_row(metric, now)
            for metric in metrics
            if metric.origin in _RECOVERY_ORIGINS
        ]
        if direct_rows:
            self.connection.executemany(
                """
                INSERT INTO financial_metrics (
                    company_id,
                    filing_id,
                    accession_number,
                    raw_fact_id,
                    origin,
                    recovery_application_id,
                    statement_type,
                    metric_name,
                    value_numeric,
                    value_raw,
                    unit,
                    period_type,
                    fiscal_year,
                    fiscal_period,
                    start_date,
                    end_date,
                    filing_date,
                    is_active_window,
                    created_at
                )
                VALUES (
                    :company_id,
                    :filing_id,
                    :accession_number,
                    :raw_fact_id,
                    :origin,
                    :recovery_application_id,
                    :statement_type,
                    :metric_name,
                    :value_numeric,
                    :value_raw,
                    :unit,
                    :period_type,
                    :fiscal_year,
                    :fiscal_period,
                    :start_date,
                    :end_date,
                    :filing_date,
                    :is_active_window,
                    :created_at
                )
                ON CONFLICT(
                    company_id,
                    metric_name,
                    period_type,
                    fiscal_year,
                    fiscal_period,
                    accession_number,
                    raw_fact_id
                )
                DO UPDATE SET
                    filing_id = excluded.filing_id,
                    statement_type = excluded.statement_type,
                    value_numeric = excluded.value_numeric,
                    value_raw = excluded.value_raw,
                    unit = excluded.unit,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    filing_date = excluded.filing_date,
                    is_active_window = excluded.is_active_window,
                    origin = excluded.origin,
                    recovery_application_id = excluded.recovery_application_id,
                    created_at = excluded.created_at
                """,
                direct_rows,
            )
        if recovered_rows:
            self.connection.executemany(
                """
                INSERT INTO financial_metrics (
                    company_id,
                    filing_id,
                    accession_number,
                    raw_fact_id,
                    origin,
                    recovery_application_id,
                    statement_type,
                    metric_name,
                    value_numeric,
                    value_raw,
                    unit,
                    period_type,
                    fiscal_year,
                    fiscal_period,
                    start_date,
                    end_date,
                    filing_date,
                    is_active_window,
                    created_at
                )
                VALUES (
                    :company_id,
                    :filing_id,
                    :accession_number,
                    :raw_fact_id,
                    :origin,
                    :recovery_application_id,
                    :statement_type,
                    :metric_name,
                    :value_numeric,
                    :value_raw,
                    :unit,
                    :period_type,
                    :fiscal_year,
                    :fiscal_period,
                    :start_date,
                    :end_date,
                    :filing_date,
                    :is_active_window,
                    :created_at
                )
                ON CONFLICT(recovery_application_id)
                DO UPDATE SET
                    company_id = excluded.company_id,
                    filing_id = excluded.filing_id,
                    accession_number = excluded.accession_number,
                    raw_fact_id = excluded.raw_fact_id,
                    origin = excluded.origin,
                    statement_type = excluded.statement_type,
                    metric_name = excluded.metric_name,
                    value_numeric = excluded.value_numeric,
                    value_raw = excluded.value_raw,
                    unit = excluded.unit,
                    period_type = excluded.period_type,
                    fiscal_year = excluded.fiscal_year,
                    fiscal_period = excluded.fiscal_period,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    filing_date = excluded.filing_date,
                    is_active_window = excluded.is_active_window,
                    created_at = excluded.created_at
                """,
                recovered_rows,
            )
        if commit:
            self.connection.commit()
        return len(metrics)

    def list_metrics(
        self,
        company_id: int,
        statement_type: str | None = None,
        metric_names: set[str] | None = None,
        *,
        active_only: bool = True,
    ) -> list[FinancialMetric]:
        """List base metrics for a company, active-window scoped by default."""
        params: list[Any] = [company_id]
        query = "SELECT * FROM financial_metrics WHERE company_id = ?"
        if statement_type is not None:
            query += " AND statement_type = ?"
            params.append(statement_type)
        if metric_names:
            names = sorted(metric_names)
            placeholders = ", ".join("?" for _ in names)
            query += f" AND metric_name IN ({placeholders})"
            params.extend(names)
        if active_only:
            query += " AND is_active_window = 1"
        query += """
            ORDER BY
                statement_type,
                metric_name,
                fiscal_year DESC,
                fiscal_period DESC,
                accession_number DESC
        """
        rows = self.connection.execute(query, params).fetchall()
        return [_row_to_metric(row) for row in rows]

    def delete_by_company_id(self, company_id: int) -> int:
        """Delete base financial metrics for one company and return deleted row count."""
        cursor = self.connection.execute(
            "DELETE FROM financial_metrics WHERE company_id = ?",
            [company_id],
        )
        self.connection.commit()
        return cursor.rowcount


def _metric_to_row(metric: FinancialMetric, now: str) -> dict[str, Any]:
    return {
        "company_id": metric.company_id,
        "filing_id": metric.filing_id,
        "accession_number": metric.accession_number,
        "raw_fact_id": metric.raw_fact_id,
        "origin": metric.origin,
        "recovery_application_id": metric.recovery_application_id,
        "statement_type": metric.statement_type,
        "metric_name": metric.metric_name,
        "value_numeric": str(metric.value_numeric) if metric.value_numeric is not None else None,
        "value_raw": json.dumps(metric.value_raw, default=str),
        "unit": metric.unit,
        "period_type": metric.period_type,
        "fiscal_year": metric.fiscal_year,
        "fiscal_period": metric.fiscal_period,
        "start_date": _date_to_text(metric.start_date),
        "end_date": _date_to_text(metric.end_date),
        "filing_date": _date_to_text(metric.filing_date),
        "is_active_window": 1 if metric.is_active_window else 0,
        "created_at": metric.created_at or now,
    }


def _row_to_metric(row: sqlite3.Row) -> FinancialMetric:
    value_numeric = row["value_numeric"]
    return FinancialMetric(
        metric_id=row["metric_id"],
        company_id=row["company_id"],
        filing_id=row["filing_id"],
        accession_number=row["accession_number"],
        raw_fact_id=row["raw_fact_id"],
        origin=row["origin"],
        recovery_application_id=row["recovery_application_id"],
        statement_type=row["statement_type"],
        metric_name=row["metric_name"],
        value_numeric=Decimal(value_numeric) if value_numeric is not None else None,
        value_raw=json.loads(row["value_raw"]),
        unit=row["unit"],
        period_type=row["period_type"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        start_date=_text_to_date(row["start_date"]),
        end_date=_text_to_date(row["end_date"]),
        filing_date=_text_to_date(row["filing_date"]),
        is_active_window=bool(row["is_active_window"]),
        created_at=row["created_at"],
    )


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _validate_metric_provenance(
    metric: FinancialMetric,
    connection: sqlite3.Connection,
) -> None:
    if metric.origin in _RECOVERY_ORIGINS:
        if metric.recovery_application_id is None:
            raise ValueError(
                "recovered metric requires recovery_application_id"
            )
        if metric.raw_fact_id is not None:
            raise ValueError(
                "recovered metric cannot point to one reported raw fact"
            )
        application_row = connection.execute(
            """
            SELECT
                recovery_application_records.record_json,
                companies.cik
            FROM recovery_application_records
            JOIN companies ON companies.company_id = ?
            WHERE recovery_application_records.recovery_application_id = ?
            """,
            [metric.company_id, metric.recovery_application_id],
        ).fetchone()
        if application_row is None:
            raise ValueError(
                "recovered metric requires an existing recovery application"
            )
        application = recovery_application_from_json(
            application_row["record_json"]
        )
        expected_origin = (
            METRIC_ORIGIN_FORMULA_RECOVERY
            if application.decision == "formula"
            else METRIC_ORIGIN_AFFIRMATIVE_ZERO_RECOVERY
            if application.decision == "zero"
            else None
        )
        if (
            application.status != RECOVERY_APPLICATION_SUCCEEDED
            or not same_cik(application.company_id, application_row["cik"])
            or metric.origin != expected_origin
            or metric.statement_type != application.statement_type
            or metric.metric_name != application.target_metric_name
            or metric.value_numeric != application.value_numeric
            or metric.unit != application.unit
            or metric.period_type != application.period_type
            or metric.fiscal_year != application.fiscal_year
            or metric.fiscal_period != application.fiscal_period
            or metric.start_date != application.start_date
            or metric.end_date != application.end_date
            or metric.filing_date != application.filing_date
            or metric.accession_number
            != recovery_metric_source_accession(application)
        ):
            raise ValueError(
                "recovered metric does not match recovery application"
            )
        return
    if metric.origin != METRIC_ORIGIN_REPORTED_MAPPING:
        raise ValueError(f"unsupported metric origin: {metric.origin}")
    if metric.recovery_application_id is not None:
        raise ValueError(
            "reported metric cannot point to a recovery application"
        )
    if metric.raw_fact_id is None:
        raise ValueError("reported metric requires raw_fact_id")
