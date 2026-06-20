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
