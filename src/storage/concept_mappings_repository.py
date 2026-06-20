"""SQLite persistence for governed XBRL concept mapping decisions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from src.storage.database import initialize_database

MAPPING_STATUS_CANDIDATE = "candidate"
MAPPING_STATUS_APPROVED = "approved"
MAPPING_STATUS_REJECTED = "rejected"
MAPPING_STATUSES = {
    MAPPING_STATUS_CANDIDATE,
    MAPPING_STATUS_APPROVED,
    MAPPING_STATUS_REJECTED,
}

MAPPING_SCOPE_GLOBAL = "global"
MAPPING_SCOPE_INDUSTRY = "industry"
MAPPING_SCOPE_COMPANY = "company"
MAPPING_SCOPES = {
    MAPPING_SCOPE_GLOBAL,
    MAPPING_SCOPE_INDUSTRY,
    MAPPING_SCOPE_COMPANY,
}


@dataclass(frozen=True)
class ConceptMappingRecord:
    """One candidate or reviewed raw-concept mapping."""

    taxonomy: str
    concept: str
    metric_name: str
    statement_type: str
    scope_type: str
    scope_value: str
    status: str
    match_method: str
    namespace_uri: str | None = None
    confidence: float | None = None
    evidence: dict[str, Any] | None = None
    mapping_id: int | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class ConceptMappingRepository:
    """Persist candidates and expose only approved mappings to calculations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        initialize_database(self.connection)

    def upsert_mappings(self, mappings: Iterable[ConceptMappingRecord]) -> int:
        rows = tuple(mappings)
        if not rows:
            return 0
        for mapping in rows:
            _validate_mapping(mapping)
        now = datetime.now(timezone.utc).isoformat()
        self.connection.executemany(
            """
            INSERT INTO xbrl_concept_mappings (
                taxonomy,
                concept,
                namespace_uri,
                metric_name,
                statement_type,
                scope_type,
                scope_value,
                status,
                confidence,
                match_method,
                evidence_json,
                reviewed_by,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                taxonomy,
                concept,
                metric_name,
                scope_type,
                scope_value
            ) DO UPDATE SET
                namespace_uri = excluded.namespace_uri,
                statement_type = excluded.statement_type,
                confidence = excluded.confidence,
                match_method = excluded.match_method,
                evidence_json = excluded.evidence_json,
                updated_at = excluded.updated_at
            WHERE xbrl_concept_mappings.status = 'candidate'
            """,
            [
                (
                    mapping.taxonomy,
                    mapping.concept,
                    mapping.namespace_uri,
                    mapping.metric_name,
                    mapping.statement_type,
                    mapping.scope_type,
                    mapping.scope_value,
                    mapping.status,
                    mapping.confidence,
                    mapping.match_method,
                    json.dumps(mapping.evidence or {}, sort_keys=True),
                    mapping.reviewed_by,
                    mapping.reviewed_at,
                    now,
                    now,
                )
                for mapping in rows
            ],
        )
        self.connection.commit()
        return len(rows)

    def list_for_company(
        self,
        cik: str,
        industry_labels: Iterable[str],
        *,
        status: str | None = None,
    ) -> tuple[ConceptMappingRecord, ...]:
        labels = tuple(dict.fromkeys(industry_labels))
        conditions = ["scope_type = 'global'", "(scope_type = 'company' AND scope_value = ?)"]
        params: list[object] = [cik]
        if labels:
            placeholders = ", ".join("?" for _ in labels)
            conditions.append(
                f"(scope_type = 'industry' AND scope_value IN ({placeholders}))"
            )
            params.extend(labels)
        query = f"""
            SELECT *
            FROM xbrl_concept_mappings
            WHERE ({' OR '.join(conditions)})
        """
        if status is not None:
            if status not in MAPPING_STATUSES:
                raise ValueError(f"Unknown mapping status: {status}")
            query += " AND status = ?"
            params.append(status)
        query += """
            ORDER BY
                CASE scope_type
                    WHEN 'company' THEN 0
                    WHEN 'industry' THEN 1
                    ELSE 2
                END,
                confidence DESC,
                taxonomy,
                concept,
                metric_name
        """
        rows = self.connection.execute(query, params).fetchall()
        return tuple(_row_to_mapping(row) for row in rows)

    def set_status(
        self,
        mapping_id: int,
        status: str,
        *,
        reviewed_by: str,
    ) -> ConceptMappingRecord:
        """Approve or reject one candidate with an explicit reviewer."""
        if status not in {MAPPING_STATUS_APPROVED, MAPPING_STATUS_REJECTED}:
            raise ValueError("Reviewed mappings must be approved or rejected")
        reviewer = reviewed_by.strip()
        if not reviewer:
            raise ValueError("reviewed_by is required")
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.connection.execute(
            """
            UPDATE xbrl_concept_mappings
            SET status = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ?
            WHERE mapping_id = ? AND status = 'candidate'
            """,
            [status, reviewer, now, now, mapping_id],
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Candidate mapping not found or already reviewed: {mapping_id}")
        self.connection.commit()
        row = self.connection.execute(
            "SELECT * FROM xbrl_concept_mappings WHERE mapping_id = ?",
            [mapping_id],
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Reviewed mapping disappeared: {mapping_id}")
        return _row_to_mapping(row)


def _validate_mapping(mapping: ConceptMappingRecord) -> None:
    if mapping.status not in MAPPING_STATUSES:
        raise ValueError(f"Unknown mapping status: {mapping.status}")
    if mapping.scope_type not in MAPPING_SCOPES:
        raise ValueError(f"Unknown mapping scope: {mapping.scope_type}")
    if mapping.scope_type == MAPPING_SCOPE_GLOBAL and mapping.scope_value:
        raise ValueError("Global mappings must use an empty scope_value")
    if mapping.scope_type != MAPPING_SCOPE_GLOBAL and not mapping.scope_value:
        raise ValueError(f"{mapping.scope_type} mappings require scope_value")
    if mapping.status != MAPPING_STATUS_CANDIDATE and not mapping.reviewed_by:
        raise ValueError("Approved and rejected mappings require reviewed_by")


def _row_to_mapping(row: sqlite3.Row) -> ConceptMappingRecord:
    return ConceptMappingRecord(
        mapping_id=row["mapping_id"],
        taxonomy=row["taxonomy"],
        concept=row["concept"],
        namespace_uri=row["namespace_uri"],
        metric_name=row["metric_name"],
        statement_type=row["statement_type"],
        scope_type=row["scope_type"],
        scope_value=row["scope_value"],
        status=row["status"],
        confidence=row["confidence"],
        match_method=row["match_method"],
        evidence=json.loads(row["evidence_json"]),
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
    )
