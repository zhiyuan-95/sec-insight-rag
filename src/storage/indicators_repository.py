"""SQLite repository for derived financial indicators."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.indicators.models import IndicatorResult
from src.storage.database import initialize_database


class FinancialIndicatorRepository:
    """Persist and retrieve derived financial indicators."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)

    def upsert_indicators(self, indicators: list[IndicatorResult]) -> int:
        """Insert or update derived indicators by formula version and period."""
        if not indicators:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [_indicator_to_row(indicator, now) for indicator in indicators]
        self.connection.executemany(
            """
            INSERT INTO financial_indicators (
                company_id,
                indicator_name,
                formula_name,
                formula_version,
                value_numeric,
                unit,
                period_type,
                fiscal_year,
                fiscal_period,
                start_date,
                end_date,
                filing_date,
                source_metric_ids,
                source_raw_fact_ids,
                source_accession_numbers,
                is_active_window,
                calculation_status,
                skip_reason,
                created_at
            )
            VALUES (
                :company_id,
                :indicator_name,
                :formula_name,
                :formula_version,
                :value_numeric,
                :unit,
                :period_type,
                :fiscal_year,
                :fiscal_period,
                :start_date,
                :end_date,
                :filing_date,
                :source_metric_ids,
                :source_raw_fact_ids,
                :source_accession_numbers,
                :is_active_window,
                :calculation_status,
                :skip_reason,
                :created_at
            )
            ON CONFLICT(
                company_id,
                indicator_name,
                period_type,
                fiscal_year,
                fiscal_period,
                formula_version
            )
            DO UPDATE SET
                formula_name = excluded.formula_name,
                value_numeric = excluded.value_numeric,
                unit = excluded.unit,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                filing_date = excluded.filing_date,
                source_metric_ids = excluded.source_metric_ids,
                source_raw_fact_ids = excluded.source_raw_fact_ids,
                source_accession_numbers = excluded.source_accession_numbers,
                is_active_window = excluded.is_active_window,
                calculation_status = excluded.calculation_status,
                skip_reason = excluded.skip_reason,
                created_at = excluded.created_at
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def list_indicators(
        self,
        company_id: int,
        indicator_names: set[str] | None = None,
        *,
        active_only: bool = True,
    ) -> list[IndicatorResult]:
        """List derived indicators for a company, active-window scoped by default."""
        params: list[Any] = [company_id]
        query = "SELECT * FROM financial_indicators WHERE company_id = ?"
        if indicator_names:
            names = sorted(indicator_names)
            placeholders = ", ".join("?" for _ in names)
            query += f" AND indicator_name IN ({placeholders})"
            params.extend(names)
        if active_only:
            query += " AND is_active_window = 1"
        query += """
            ORDER BY
                fiscal_year DESC,
                fiscal_period DESC,
                indicator_name
        """
        rows = self.connection.execute(query, params).fetchall()
        return [_row_to_indicator(row) for row in rows]

    def deactivate_by_company_id(self, company_id: int) -> int:
        """Mark existing company indicators inactive before a fresh active-window upsert."""
        cursor = self.connection.execute(
            "UPDATE financial_indicators SET is_active_window = 0 WHERE company_id = ?",
            [company_id],
        )
        self.connection.commit()
        return cursor.rowcount

    def delete_by_company_id(self, company_id: int) -> int:
        """Delete derived indicators for one company and return deleted row count."""
        cursor = self.connection.execute("DELETE FROM financial_indicators WHERE company_id = ?", [company_id])
        self.connection.commit()
        return cursor.rowcount


def _indicator_to_row(indicator: IndicatorResult, now: str) -> dict[str, Any]:
    return {
        "company_id": indicator.company_id,
        "indicator_name": indicator.indicator_name,
        "formula_name": indicator.formula_name,
        "formula_version": indicator.formula_version,
        "value_numeric": str(indicator.value_numeric) if indicator.value_numeric is not None else None,
        "unit": indicator.unit,
        "period_type": indicator.period_type,
        "fiscal_year": indicator.fiscal_year,
        "fiscal_period": indicator.fiscal_period,
        "start_date": _date_to_text(indicator.start_date),
        "end_date": _date_to_text(indicator.end_date),
        "filing_date": _date_to_text(indicator.filing_date),
        "source_metric_ids": json.dumps(list(indicator.source_metric_ids)),
        "source_raw_fact_ids": json.dumps(list(indicator.source_raw_fact_ids)),
        "source_accession_numbers": json.dumps(list(indicator.source_accession_numbers)),
        "is_active_window": 1 if indicator.is_active_window else 0,
        "calculation_status": indicator.calculation_status,
        "skip_reason": indicator.skip_reason,
        "created_at": now,
    }


def _row_to_indicator(row: sqlite3.Row) -> IndicatorResult:
    value_numeric = row["value_numeric"]
    return IndicatorResult(
        company_id=row["company_id"],
        indicator_name=row["indicator_name"],
        formula_name=row["formula_name"],
        formula_version=row["formula_version"],
        value_numeric=Decimal(value_numeric) if value_numeric is not None else None,
        unit=row["unit"],
        period_type=row["period_type"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        start_date=_text_to_date(row["start_date"]),
        end_date=_text_to_date(row["end_date"]),
        filing_date=_text_to_date(row["filing_date"]),
        source_metric_ids=tuple(json.loads(row["source_metric_ids"])),
        source_raw_fact_ids=tuple(json.loads(row["source_raw_fact_ids"])),
        source_accession_numbers=tuple(json.loads(row["source_accession_numbers"])),
        is_active_window=bool(row["is_active_window"]),
        calculation_status=row["calculation_status"],
        skip_reason=row["skip_reason"],
    )


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
