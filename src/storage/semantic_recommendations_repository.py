"""SQLite persistence for immutable semantic recommendation group records."""

from __future__ import annotations

import sqlite3

from src.processing.semantic_recommendations import (
    SemanticRecommendationRecord,
    semantic_recommendation_record_from_json,
    semantic_recommendation_record_to_json,
)
from src.storage.database import initialize_database


class SemanticRecommendationConflictError(RuntimeError):
    """Raised when an immutable recommendation request is rewritten."""


class SemanticRecommendationRepository:
    """Persist and retrieve reusable group-level judge recommendations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        initialize_database(self.connection)

    def insert(self, record: SemanticRecommendationRecord) -> bool:
        """Insert one immutable record, returning False for an exact replay."""
        if record.attempt_number < 1:
            raise ValueError("attempt_number must be at least 1")
        existing = self.get_attempt(
            record.recommendation_request_id,
            record.attempt_number,
        )
        if existing is not None:
            if existing == record:
                return False
            raise SemanticRecommendationConflictError(
                "Cannot replace immutable semantic recommendation "
                f"{record.recommendation_request_id}"
            )
        record_json = semantic_recommendation_record_to_json(record)
        try:
            self.connection.execute(
                """
                INSERT INTO semantic_recommendation_records (
                    recommendation_request_id,
                    attempt_number,
                    company_id,
                    packet_content_sha256,
                    outcome,
                    record_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.recommendation_request_id,
                    record.attempt_number,
                    record.company_id,
                    record.packet_content_sha256,
                    record.outcome,
                    record_json,
                    record.created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            concurrent = self.get_attempt(
                record.recommendation_request_id,
                record.attempt_number,
            )
            if concurrent == record:
                return False
            if concurrent is None:
                raise
            raise SemanticRecommendationConflictError(
                "Cannot replace immutable semantic recommendation "
                f"{record.recommendation_request_id}"
            ) from exc
        self.connection.commit()
        return True

    def get(
        self,
        recommendation_request_id: str,
    ) -> SemanticRecommendationRecord | None:
        """Return one exact historical recommendation group record."""
        row = self.connection.execute(
            """
            SELECT record_json
            FROM semantic_recommendation_records
            WHERE recommendation_request_id = ?
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (recommendation_request_id,),
        ).fetchone()
        if row is None:
            return None
        return semantic_recommendation_record_from_json(row["record_json"])

    def get_attempt(
        self,
        recommendation_request_id: str,
        attempt_number: int,
    ) -> SemanticRecommendationRecord | None:
        """Return one immutable attempt within a recommendation group."""
        row = self.connection.execute(
            """
            SELECT record_json
            FROM semantic_recommendation_records
            WHERE recommendation_request_id = ?
              AND attempt_number = ?
            """,
            (recommendation_request_id, attempt_number),
        ).fetchone()
        if row is None:
            return None
        return semantic_recommendation_record_from_json(row["record_json"])

    def list_attempts(
        self,
        recommendation_request_id: str,
    ) -> tuple[SemanticRecommendationRecord, ...]:
        """Return the immutable chronological attempt history for one group."""
        rows = self.connection.execute(
            """
            SELECT record_json
            FROM semantic_recommendation_records
            WHERE recommendation_request_id = ?
            ORDER BY attempt_number
            """,
            (recommendation_request_id,),
        ).fetchall()
        return tuple(
            semantic_recommendation_record_from_json(row["record_json"])
            for row in rows
        )
