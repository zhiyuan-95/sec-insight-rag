"""SQLite repository for local company registry and refresh state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from src.storage.database import initialize_database


@dataclass(frozen=True)
class CompanyRecord:
    """A locally tracked company and its SEC refresh state."""

    cik: str
    name: str
    company_id: int | None = None
    ticker: str | None = None
    exchange: str | None = None
    sic: str | None = None
    sic_description: str | None = None
    latest_10k_filing_date: date | None = None
    latest_10q_filing_date: date | None = None
    next_check_date_10k: date | None = None
    next_check_date_10q: date | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CompanyRepository:
    """Persist and retrieve local company registry records."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)

    def get_by_cik(self, cik: str) -> CompanyRecord | None:
        """Return one company by CIK, if present."""
        row = self.connection.execute("SELECT * FROM companies WHERE cik = ?", [cik]).fetchone()
        return _row_to_company(row) if row is not None else None

    def get_by_ticker(self, ticker: str) -> CompanyRecord | None:
        """Return one company by ticker, if present."""
        row = self.connection.execute(
            "SELECT * FROM companies WHERE ticker = ? COLLATE NOCASE ORDER BY company_id LIMIT 1",
            [ticker.strip().upper()],
        ).fetchone()
        return _row_to_company(row) if row is not None else None

    def upsert_company(self, company: CompanyRecord) -> CompanyRecord:
        """Insert or update a company by CIK and return the stored row."""
        now = datetime.now(timezone.utc).isoformat()
        row = _company_to_row(company, now)
        self.connection.execute(
            """
            INSERT INTO companies (
                cik,
                name,
                ticker,
                exchange,
                sic,
                sic_description,
                latest_10k_filing_date,
                latest_10q_filing_date,
                next_check_date_10k,
                next_check_date_10q,
                created_at,
                updated_at
            )
            VALUES (
                :cik,
                :name,
                :ticker,
                :exchange,
                :sic,
                :sic_description,
                :latest_10k_filing_date,
                :latest_10q_filing_date,
                :next_check_date_10k,
                :next_check_date_10q,
                :created_at,
                :updated_at
            )
            ON CONFLICT(cik) DO UPDATE SET
                name = excluded.name,
                ticker = excluded.ticker,
                exchange = excluded.exchange,
                sic = excluded.sic,
                sic_description = excluded.sic_description,
                latest_10k_filing_date = excluded.latest_10k_filing_date,
                latest_10q_filing_date = excluded.latest_10q_filing_date,
                next_check_date_10k = excluded.next_check_date_10k,
                next_check_date_10q = excluded.next_check_date_10q,
                updated_at = excluded.updated_at
            """,
            row,
        )
        self.connection.commit()
        stored = self.get_by_cik(company.cik)
        if stored is None:
            raise RuntimeError(f"Company upsert did not return a stored row for CIK {company.cik}")
        return stored

    def update_check_state(
        self,
        company_id: int,
        *,
        latest_10k_filing_date: date | None = None,
        latest_10q_filing_date: date | None = None,
        next_check_date_10k: date | None = None,
        next_check_date_10q: date | None = None,
    ) -> None:
        """Update filing freshness dates for a stored company."""
        updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if latest_10k_filing_date is not None:
            updates["latest_10k_filing_date"] = latest_10k_filing_date.isoformat()
        if latest_10q_filing_date is not None:
            updates["latest_10q_filing_date"] = latest_10q_filing_date.isoformat()
        if next_check_date_10k is not None:
            updates["next_check_date_10k"] = next_check_date_10k.isoformat()
        if next_check_date_10q is not None:
            updates["next_check_date_10q"] = next_check_date_10q.isoformat()
        if len(updates) == 1:
            return

        assignments = ", ".join(f"{column} = :{column}" for column in updates)
        updates["company_id"] = company_id
        self.connection.execute(f"UPDATE companies SET {assignments} WHERE company_id = :company_id", updates)
        self.connection.commit()

    def delete_by_cik(self, cik: str) -> int:
        """Delete one company registry row by CIK and return deleted row count."""
        cursor = self.connection.execute("DELETE FROM companies WHERE cik = ?", [cik])
        self.connection.commit()
        return cursor.rowcount


def _company_to_row(company: CompanyRecord, now: str) -> dict[str, Any]:
    created_at = company.created_at or now
    return {
        "cik": company.cik,
        "name": company.name,
        "ticker": company.ticker.strip().upper() if company.ticker else None,
        "exchange": company.exchange,
        "sic": company.sic,
        "sic_description": company.sic_description,
        "latest_10k_filing_date": _date_to_text(company.latest_10k_filing_date),
        "latest_10q_filing_date": _date_to_text(company.latest_10q_filing_date),
        "next_check_date_10k": _date_to_text(company.next_check_date_10k),
        "next_check_date_10q": _date_to_text(company.next_check_date_10q),
        "created_at": created_at,
        "updated_at": now,
    }


def _row_to_company(row: sqlite3.Row) -> CompanyRecord:
    return CompanyRecord(
        company_id=row["company_id"],
        cik=row["cik"],
        name=row["name"],
        ticker=row["ticker"],
        exchange=row["exchange"],
        sic=row["sic"],
        sic_description=row["sic_description"],
        latest_10k_filing_date=_text_to_date(row["latest_10k_filing_date"]),
        latest_10q_filing_date=_text_to_date(row["latest_10q_filing_date"]),
        next_check_date_10k=_text_to_date(row["next_check_date_10k"]),
        next_check_date_10q=_text_to_date(row["next_check_date_10q"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
