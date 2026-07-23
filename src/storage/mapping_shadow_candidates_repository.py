"""SQLite persistence for non-authoritative metric-mapping suggestions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.processing.direct_metric_mapping import ShadowMappingCandidate
from src.storage.database import initialize_database


@dataclass(frozen=True)
class StoredMappingShadowCandidate:
    """One period-scoped shadow candidate retained for inspection only."""

    company_id: int
    raw_fact_id: int
    taxonomy: str
    concept: str
    metric_name: str
    statement_type: str
    fiscal_year: int
    fiscal_period: str
    score: float
    match_method: str
    evidence: dict[str, Any]
    shadow_candidate_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MappingShadowCandidateRepository:
    """Persist and inspect candidates that never populate financial metrics."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        initialize_database(self.connection)

    def upsert_candidates(
        self,
        candidates: Iterable[StoredMappingShadowCandidate],
    ) -> int:
        rows = tuple(candidates)
        if not rows:
            return 0
        for candidate in rows:
            _validate_candidate(candidate)
        now = datetime.now(timezone.utc).isoformat()
        self.connection.executemany(
            """
            INSERT INTO mapping_shadow_candidates (
                company_id,
                raw_fact_id,
                taxonomy,
                concept,
                metric_name,
                statement_type,
                fiscal_year,
                fiscal_period,
                score,
                match_method,
                evidence_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                company_id,
                raw_fact_id,
                metric_name,
                match_method
            ) DO UPDATE SET
                taxonomy = excluded.taxonomy,
                concept = excluded.concept,
                statement_type = excluded.statement_type,
                fiscal_year = excluded.fiscal_year,
                fiscal_period = excluded.fiscal_period,
                score = excluded.score,
                evidence_json = excluded.evidence_json,
                updated_at = excluded.updated_at
            """,
            [
                (
                    candidate.company_id,
                    candidate.raw_fact_id,
                    candidate.taxonomy,
                    candidate.concept,
                    candidate.metric_name,
                    candidate.statement_type,
                    candidate.fiscal_year,
                    candidate.fiscal_period,
                    candidate.score,
                    candidate.match_method,
                    json.dumps(candidate.evidence, sort_keys=True),
                    candidate.created_at or now,
                    candidate.updated_at or now,
                )
                for candidate in rows
            ],
        )
        self.connection.commit()
        return len(rows)

    def upsert_period_candidates(
        self,
        *,
        company_id: int,
        fiscal_year: int,
        fiscal_period: str,
        candidates: Iterable[ShadowMappingCandidate],
    ) -> int:
        """Persist shadow candidates returned by the period-mapping seam."""
        return self.upsert_candidates(
            StoredMappingShadowCandidate(
                company_id=company_id,
                raw_fact_id=candidate.raw_fact_id,
                taxonomy=candidate.taxonomy,
                concept=candidate.concept,
                metric_name=candidate.metric_name,
                statement_type=candidate.statement_type,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                score=candidate.score,
                match_method=candidate.match_method,
                evidence=candidate.evidence,
            )
            for candidate in candidates
        )

    def list_for_period(
        self,
        *,
        company_id: int,
        fiscal_year: int,
        fiscal_period: str,
    ) -> tuple[StoredMappingShadowCandidate, ...]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM mapping_shadow_candidates
            WHERE company_id = ?
              AND fiscal_year = ?
              AND fiscal_period = ?
            ORDER BY
                metric_name,
                score DESC,
                taxonomy,
                concept,
                raw_fact_id
            """,
            (company_id, fiscal_year, fiscal_period),
        ).fetchall()
        return tuple(_row_to_candidate(row) for row in rows)


def _validate_candidate(candidate: StoredMappingShadowCandidate) -> None:
    if not 0.0 <= candidate.score <= 1.0:
        raise ValueError("Shadow candidate score must be between 0 and 1")
    if not candidate.match_method.strip():
        raise ValueError("Shadow candidate match_method is required")
    if candidate.evidence.get("candidate_is_authoritative") is True:
        raise ValueError("Shadow candidates cannot be authoritative")


def _row_to_candidate(row: sqlite3.Row) -> StoredMappingShadowCandidate:
    return StoredMappingShadowCandidate(
        shadow_candidate_id=row["shadow_candidate_id"],
        company_id=row["company_id"],
        raw_fact_id=row["raw_fact_id"],
        taxonomy=row["taxonomy"],
        concept=row["concept"],
        metric_name=row["metric_name"],
        statement_type=row["statement_type"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        score=row["score"],
        match_method=row["match_method"],
        evidence=json.loads(row["evidence_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
