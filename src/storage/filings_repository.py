"""SQLite repository for ingested SEC filing metadata."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.storage.database import initialize_database


@dataclass(frozen=True)
class FilingRecord:
    """A locally tracked SEC filing and active-window state."""

    company_id: int
    accession_number: str
    form_type: str
    filing_date: date
    filing_id: int | None = None
    report_date: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    source: str = "SEC"
    document_url: str | None = None
    local_path: Path | None = None
    is_active_window: bool = True
    ingested_at: str | None = None


class FilingRepository:
    """Persist and retrieve ingested filing metadata."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)

    def upsert_filings(self, company_id: int, filings: list[FilingRecord]) -> int:
        """Insert or update filings by SEC accession number."""
        if not filings:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [_filing_to_row(replace(filing, company_id=company_id), now) for filing in filings]
        self.connection.executemany(
            """
            INSERT INTO filings (
                company_id,
                accession_number,
                form_type,
                filing_date,
                report_date,
                fiscal_year,
                fiscal_period,
                source,
                document_url,
                local_path,
                is_active_window,
                ingested_at
            )
            VALUES (
                :company_id,
                :accession_number,
                :form_type,
                :filing_date,
                :report_date,
                :fiscal_year,
                :fiscal_period,
                :source,
                :document_url,
                :local_path,
                :is_active_window,
                :ingested_at
            )
            ON CONFLICT(accession_number) DO UPDATE SET
                company_id = excluded.company_id,
                form_type = excluded.form_type,
                filing_date = excluded.filing_date,
                report_date = excluded.report_date,
                fiscal_year = excluded.fiscal_year,
                fiscal_period = excluded.fiscal_period,
                source = excluded.source,
                document_url = excluded.document_url,
                local_path = excluded.local_path,
                is_active_window = excluded.is_active_window,
                ingested_at = excluded.ingested_at
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def list_filings(
        self,
        company_id: int,
        forms: set[str] | None = None,
        *,
        active_only: bool = False,
    ) -> list[FilingRecord]:
        """List stored filings for a company."""
        params: list[Any] = [company_id]
        query = "SELECT * FROM filings WHERE company_id = ?"
        if forms:
            normalized_forms = sorted(form.strip().upper() for form in forms)
            placeholders = ", ".join("?" for _ in normalized_forms)
            query += f" AND form_type IN ({placeholders})"
            params.extend(normalized_forms)
        if active_only:
            query += " AND is_active_window = 1"
        query += " ORDER BY filing_date DESC, accession_number DESC"
        rows = self.connection.execute(query, params).fetchall()
        return [_row_to_filing(row) for row in rows]

    def delete_by_company_id(self, company_id: int) -> int:
        """Delete filing metadata for one company and return deleted row count."""
        cursor = self.connection.execute("DELETE FROM filings WHERE company_id = ?", [company_id])
        self.connection.commit()
        return cursor.rowcount

    def get_by_accession(self, accession_number: str) -> FilingRecord | None:
        """Return one filing by accession number, if present."""
        row = self.connection.execute(
            "SELECT * FROM filings WHERE accession_number = ?",
            [accession_number],
        ).fetchone()
        return _row_to_filing(row) if row is not None else None

    def set_active_window(self, company_id: int, active_accessions: set[str]) -> None:
        """Mark company filings active only when their accession is in the provided set."""
        self.connection.execute(
            "UPDATE filings SET is_active_window = 0 WHERE company_id = ?",
            [company_id],
        )
        if active_accessions:
            placeholders = ", ".join("?" for _ in active_accessions)
            self.connection.execute(
                f"""
                UPDATE filings
                SET is_active_window = 1
                WHERE company_id = ? AND accession_number IN ({placeholders})
                """,
                [company_id, *sorted(active_accessions)],
            )
        self.connection.commit()


def _filing_to_row(filing: FilingRecord, now: str) -> dict[str, Any]:
    return {
        "company_id": filing.company_id,
        "accession_number": filing.accession_number,
        "form_type": filing.form_type.strip().upper(),
        "filing_date": filing.filing_date.isoformat(),
        "report_date": _date_to_text(filing.report_date),
        "fiscal_year": filing.fiscal_year,
        "fiscal_period": filing.fiscal_period,
        "source": filing.source,
        "document_url": filing.document_url,
        "local_path": str(filing.local_path) if filing.local_path is not None else None,
        "is_active_window": 1 if filing.is_active_window else 0,
        "ingested_at": filing.ingested_at or now,
    }


def _row_to_filing(row: sqlite3.Row) -> FilingRecord:
    local_path = Path(row["local_path"]) if row["local_path"] else None
    return FilingRecord(
        filing_id=row["filing_id"],
        company_id=row["company_id"],
        accession_number=row["accession_number"],
        form_type=row["form_type"],
        filing_date=date.fromisoformat(row["filing_date"]),
        report_date=_text_to_date(row["report_date"]),
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        source=row["source"],
        document_url=row["document_url"],
        local_path=local_path,
        is_active_window=bool(row["is_active_window"]),
        ingested_at=row["ingested_at"],
    )


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
