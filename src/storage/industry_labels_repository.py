"""SQLite persistence for reusable company industry labels."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src.storage.database import initialize_database


@dataclass(frozen=True)
class StoredCompanyIndustryLabel:
    """One persisted hard-industry label and its assignment evidence."""

    company_id: int
    industry_label: str
    assignment_source: str
    assignment_reason: str
    status: str = "approved"
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    classifier_version: str | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class StoredFiscalPeriodIndustryLabelSnapshot:
    """One immutable industry-label decision for an original annual period."""

    company_id: int
    accession_number: str
    fiscal_year: int
    fiscal_period: str
    assigned_industry_labels: tuple[str, ...]
    assignment_source: str
    assignment_reason: str
    label_status: str
    confidence: float | None = None
    evidence: tuple[str, ...] = ()
    classifier_version: str | None = None
    reviewed_at: str | None = None


class IndustryLabelSnapshotConflictError(RuntimeError):
    """Raised when a caller tries to rewrite an immutable period snapshot."""


class CompanyIndustryLabelRepository:
    """Persist and retrieve company hard-industry labels."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        initialize_database(self.connection)

    def replace_labels(
        self,
        company_id: int,
        labels: tuple[StoredCompanyIndustryLabel, ...],
    ) -> int:
        """Replace one company's labels while preserving explicit evidence."""
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "DELETE FROM company_industry_labels WHERE company_id = ?",
            [company_id],
        )
        if labels:
            self.connection.executemany(
                """
                INSERT INTO company_industry_labels (
                    company_id,
                    industry_label,
                    status,
                    assignment_source,
                    assignment_reason,
                    confidence,
                    evidence_json,
                    classifier_version,
                    reviewed_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        label.company_id,
                        label.industry_label,
                        label.status,
                        label.assignment_source,
                        label.assignment_reason,
                        label.confidence,
                        json.dumps(list(label.evidence)),
                        label.classifier_version,
                        label.reviewed_at,
                        now,
                        now,
                    )
                    for label in labels
                ],
            )
        self.connection.commit()
        return len(labels)

    def list_labels(
        self,
        company_id: int,
        *,
        status: str | None = "approved",
    ) -> tuple[StoredCompanyIndustryLabel, ...]:
        query = "SELECT * FROM company_industry_labels WHERE company_id = ?"
        params: list[object] = [company_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY industry_label"
        rows = self.connection.execute(query, params).fetchall()
        return tuple(
            StoredCompanyIndustryLabel(
                company_id=row["company_id"],
                industry_label=row["industry_label"],
                status=row["status"],
                assignment_source=row["assignment_source"],
                assignment_reason=row["assignment_reason"],
                confidence=row["confidence"],
                evidence=tuple(json.loads(row["evidence_json"])),
                classifier_version=row["classifier_version"],
                reviewed_at=row["reviewed_at"],
            )
            for row in rows
        )

    def insert_period_snapshot(
        self,
        snapshot: StoredFiscalPeriodIndustryLabelSnapshot,
    ) -> bool:
        """Insert one immutable snapshot, returning False for an exact replay."""
        existing = self.get_period_snapshot(
            company_id=snapshot.company_id,
            accession_number=snapshot.accession_number,
            fiscal_year=snapshot.fiscal_year,
            fiscal_period=snapshot.fiscal_period,
        )
        if existing is not None:
            if existing == snapshot:
                return False
            raise IndustryLabelSnapshotConflictError(
                "Cannot replace immutable industry-label snapshot for "
                f"{snapshot.accession_number} "
                f"{snapshot.fiscal_year} {snapshot.fiscal_period}"
            )

        now = datetime.now(timezone.utc).isoformat()
        try:
            self.connection.execute(
                """
                INSERT INTO company_industry_label_snapshots (
                    company_id,
                    accession_number,
                    fiscal_year,
                    fiscal_period,
                    assigned_labels_json,
                    label_status,
                    assignment_source,
                    assignment_reason,
                    confidence,
                    evidence_json,
                    classifier_version,
                    reviewed_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.company_id,
                    snapshot.accession_number,
                    snapshot.fiscal_year,
                    snapshot.fiscal_period,
                    json.dumps(list(snapshot.assigned_industry_labels)),
                    snapshot.label_status,
                    snapshot.assignment_source,
                    snapshot.assignment_reason,
                    snapshot.confidence,
                    json.dumps(list(snapshot.evidence)),
                    snapshot.classifier_version,
                    snapshot.reviewed_at,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            concurrent = self.get_period_snapshot(
                company_id=snapshot.company_id,
                accession_number=snapshot.accession_number,
                fiscal_year=snapshot.fiscal_year,
                fiscal_period=snapshot.fiscal_period,
            )
            if concurrent == snapshot:
                return False
            if concurrent is None:
                raise
            raise IndustryLabelSnapshotConflictError(
                "Cannot replace immutable industry-label snapshot for "
                f"{snapshot.accession_number} "
                f"{snapshot.fiscal_year} {snapshot.fiscal_period}"
            ) from exc
        self.connection.commit()
        return True

    def get_period_snapshot(
        self,
        *,
        company_id: int,
        accession_number: str,
        fiscal_year: int,
        fiscal_period: str,
    ) -> StoredFiscalPeriodIndustryLabelSnapshot | None:
        """Return the immutable snapshot for one original accession period."""
        row = self.connection.execute(
            """
            SELECT *
            FROM company_industry_label_snapshots
            WHERE company_id = ?
              AND accession_number = ?
              AND fiscal_year = ?
              AND fiscal_period = ?
            """,
            (
                company_id,
                accession_number,
                fiscal_year,
                fiscal_period,
            ),
        ).fetchone()
        return _row_to_period_snapshot(row) if row is not None else None

    def list_period_snapshots(
        self,
        company_id: int,
    ) -> tuple[StoredFiscalPeriodIndustryLabelSnapshot, ...]:
        """Return all immutable annual label snapshots for one company."""
        rows = self.connection.execute(
            """
            SELECT *
            FROM company_industry_label_snapshots
            WHERE company_id = ?
            ORDER BY fiscal_year, fiscal_period, accession_number
            """,
            (company_id,),
        ).fetchall()
        return tuple(_row_to_period_snapshot(row) for row in rows)


def _row_to_period_snapshot(
    row: sqlite3.Row,
) -> StoredFiscalPeriodIndustryLabelSnapshot:
    return StoredFiscalPeriodIndustryLabelSnapshot(
        company_id=row["company_id"],
        accession_number=row["accession_number"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        assigned_industry_labels=tuple(json.loads(row["assigned_labels_json"])),
        label_status=row["label_status"],
        assignment_source=row["assignment_source"],
        assignment_reason=row["assignment_reason"],
        confidence=row["confidence"],
        evidence=tuple(json.loads(row["evidence_json"])),
        classifier_version=row["classifier_version"],
        reviewed_at=row["reviewed_at"],
    )
