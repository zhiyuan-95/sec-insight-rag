"""SQLite repository for base financial metrics mapped from raw XBRL facts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.storage.database import initialize_database


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

    def upsert_metrics(self, metrics: list[FinancialMetric]) -> int:
        """Insert or update base metrics by source fact identity."""
        if not metrics:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [_metric_to_row(metric, now) for metric in metrics]
        self.connection.executemany(
            """
            INSERT INTO financial_metrics (
                company_id,
                filing_id,
                accession_number,
                raw_fact_id,
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
                created_at = excluded.created_at
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

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
        cursor = self.connection.execute("DELETE FROM financial_metrics WHERE company_id = ?", [company_id])
        self.connection.commit()
        return cursor.rowcount


def _metric_to_row(metric: FinancialMetric, now: str) -> dict[str, Any]:
    return {
        "company_id": metric.company_id,
        "filing_id": metric.filing_id,
        "accession_number": metric.accession_number,
        "raw_fact_id": metric.raw_fact_id,
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
