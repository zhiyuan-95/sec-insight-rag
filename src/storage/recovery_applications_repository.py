"""SQLite persistence for period-specific recovery applications."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from src.processing.recovery_applications import (
    AffirmativeZeroEvidence,
    RECOVERY_APPLICATION_SUCCEEDED,
    RecoveryApplication,
    RecoveryComponentApplication,
    recovery_application_from_json,
    recovery_application_to_json,
    validate_recovery_application,
)
from src.processing.company_identity import same_cik
from src.processing.xbrl_normalizer import NormalizedFact
from src.processing.semantic_recommendations import (
    RECOMMENDATION_UNANIMOUS_FORMULA,
    RECOMMENDATION_UNANIMOUS_ZERO,
    semantic_recommendation_record_from_json,
)
from src.storage.database import initialize_database
from src.storage.facts_repository import RawFactRepository


class RecoveryApplicationConflictError(RuntimeError):
    """Raised when an immutable period application would be rewritten."""


@dataclass(frozen=True)
class StoredRecoveryApplication:
    """One stored recovery application and its metric-link identifier."""

    recovery_application_id: int
    application: RecoveryApplication
    created_at: str


class RecoveryApplicationRepository:
    """Persist and retrieve immutable period application evidence."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        initialize_database(self.connection)

    def insert(
        self,
        application: RecoveryApplication,
        *,
        commit: bool = True,
    ) -> StoredRecoveryApplication:
        """Insert an immutable application or return its exact replay."""
        self._validate_recommendation_link(application)
        existing = self.get(
            recommendation_request_id=application.recommendation_request_id,
            recommendation_attempt_number=(
                application.recommendation_attempt_number
            ),
            period_id=application.period_id,
            target_metric_name=application.target_metric_name,
            statement_type=application.statement_type,
        )
        if existing is not None:
            if existing.application == application:
                return existing
            raise RecoveryApplicationConflictError(
                "Cannot replace immutable recovery application "
                f"{application.recommendation_request_id}/"
                f"{application.period_id}/"
                f"{application.target_metric_name}"
            )
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            cursor = self.connection.execute(
                """
                INSERT INTO recovery_application_records (
                    recommendation_request_id,
                    recommendation_attempt_number,
                    company_id,
                    period_id,
                    target_metric_name,
                    statement_type,
                    status,
                    record_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.recommendation_request_id,
                    application.recommendation_attempt_number,
                    application.company_id,
                    application.period_id,
                    application.target_metric_name,
                    application.statement_type,
                    application.status,
                    recovery_application_to_json(application),
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if commit:
                self.connection.rollback()
            concurrent = self.get(
                recommendation_request_id=(
                    application.recommendation_request_id
                ),
                recommendation_attempt_number=(
                    application.recommendation_attempt_number
                ),
                period_id=application.period_id,
                target_metric_name=application.target_metric_name,
                statement_type=application.statement_type,
            )
            if (
                concurrent is not None
                and concurrent.application == application
            ):
                return concurrent
            raise RecoveryApplicationConflictError(
                "Cannot replace immutable recovery application "
                f"{application.recommendation_request_id}/"
                f"{application.period_id}/"
                f"{application.target_metric_name}"
            ) from exc
        if commit:
            self.connection.commit()
        recovery_application_id = cursor.lastrowid
        if recovery_application_id is None:
            raise RuntimeError("Recovery application insert returned no ID")
        return StoredRecoveryApplication(
            recovery_application_id=int(recovery_application_id),
            application=application,
            created_at=created_at,
        )

    def get(
        self,
        *,
        recommendation_request_id: str,
        recommendation_attempt_number: int,
        period_id: str,
        target_metric_name: str,
        statement_type: str,
    ) -> StoredRecoveryApplication | None:
        """Return one exact period/target application."""
        row = self.connection.execute(
            """
            SELECT recovery_application_id, record_json, created_at
            FROM recovery_application_records
            WHERE recommendation_request_id = ?
              AND recommendation_attempt_number = ?
              AND period_id = ?
              AND target_metric_name = ?
              AND statement_type = ?
            """,
            (
                recommendation_request_id,
                recommendation_attempt_number,
                period_id,
                target_metric_name,
                statement_type,
            ),
        ).fetchone()
        return _row_to_stored_application(row) if row is not None else None

    def list_for_recommendation(
        self,
        recommendation_request_id: str,
        recommendation_attempt_number: int,
    ) -> tuple[StoredRecoveryApplication, ...]:
        """Return period applications in stable period/target order."""
        rows = self.connection.execute(
            """
            SELECT recovery_application_id, record_json, created_at
            FROM recovery_application_records
            WHERE recommendation_request_id = ?
              AND recommendation_attempt_number = ?
            ORDER BY period_id, target_metric_name, statement_type
            """,
            (
                recommendation_request_id,
                recommendation_attempt_number,
            ),
        ).fetchall()
        return tuple(_row_to_stored_application(row) for row in rows)

    def _validate_recommendation_link(
        self,
        application: RecoveryApplication,
    ) -> None:
        row = self.connection.execute(
            """
            SELECT record_json
            FROM semantic_recommendation_records
            WHERE recommendation_request_id = ?
              AND attempt_number = ?
            """,
            (
                application.recommendation_request_id,
                application.recommendation_attempt_number,
            ),
        ).fetchone()
        if row is None:
            raise ValueError(
                "recovery application has no linked recommendation"
            )
        recommendation = semantic_recommendation_record_from_json(
            row["record_json"]
        )
        comparison = next(
            (
                item
                for item in recommendation.target_comparisons
                if item.target_metric_name
                == application.target_metric_name
                and item.statement_type == application.statement_type
            ),
            None,
        )
        expected_outcome = {
            "formula": RECOMMENDATION_UNANIMOUS_FORMULA,
            "zero": RECOMMENDATION_UNANIMOUS_ZERO,
        }.get(application.decision)
        if (
            recommendation.company_id != application.company_id
            or application.period_id not in recommendation.period_ids
            or comparison is None
            or expected_outcome is None
            or comparison.outcome != expected_outcome
        ):
            raise ValueError(
                "recovery application does not match linked unanimous "
                "recommendation"
            )
        validate_recovery_application(
            application,
            comparison,
            recommendation.packet_json,
        )
        self._validate_source_fact_lineage(application)

    def _validate_source_fact_lineage(
        self,
        application: RecoveryApplication,
    ) -> None:
        if application.status != RECOVERY_APPLICATION_SUCCEEDED:
            return
        records = RawFactRepository(self.connection).get_by_ids(
            application.source_raw_fact_ids
        )
        by_id = {record.raw_fact_id: record.fact for record in records}
        if set(by_id) != set(application.source_raw_fact_ids):
            raise ValueError(
                "recovery application source raw fact lineage is incomplete"
            )
        if application.decision == "formula":
            if any(
                not _fact_matches_component(
                    by_id.get(component.raw_fact_id),
                    component,
                    application,
                )
                for component in application.components
            ):
                raise ValueError(
                    "recovery application source raw fact lineage is invalid"
                )
            return
        evidence = application.zero_evidence
        if (
            evidence is None
            or not _fact_matches_zero_evidence(
                by_id.get(evidence.raw_fact_id),
                evidence,
            )
        ):
            raise ValueError(
                "recovery application source raw fact lineage is invalid"
            )


def _row_to_stored_application(
    row: sqlite3.Row,
) -> StoredRecoveryApplication:
    return StoredRecoveryApplication(
        recovery_application_id=row["recovery_application_id"],
        application=recovery_application_from_json(row["record_json"]),
        created_at=row["created_at"],
    )


def _fact_matches_component(
    fact: NormalizedFact | None,
    component: RecoveryComponentApplication,
    application: RecoveryApplication,
) -> bool:
    return bool(
        fact is not None
        and same_cik(fact.cik, application.company_id)
        and fact.taxonomy.casefold() == component.taxonomy.casefold()
        and fact.concept == component.concept
        and fact.value == component.value_numeric
        and fact.unit.casefold() == component.unit.casefold()
        and fact.period_type == component.period_type
        and fact.start_date == component.start_date
        and fact.end_date == component.end_date
        and fact.filed_date == component.filing_date
        and fact.accession_number == component.accession_number
        and fact.source == component.source_system
        and fact.fiscal_year == application.fiscal_year
        and fact.fiscal_period == application.fiscal_period
        and fact.is_numeric is not False
        and fact.is_consolidated
        and not fact.dimensions
    )


def _fact_matches_zero_evidence(
    fact: NormalizedFact | None,
    evidence: AffirmativeZeroEvidence,
) -> bool:
    return bool(
        fact is not None
        and same_cik(fact.cik, evidence.company_id)
        and fact.taxonomy.casefold() == evidence.taxonomy.casefold()
        and fact.concept == evidence.concept
        and fact.value == evidence.value_numeric
        and fact.unit.casefold() == evidence.unit.casefold()
        and fact.period_type == evidence.period_type
        and fact.start_date == evidence.start_date
        and fact.end_date == evidence.end_date
        and fact.filed_date == evidence.filing_date
        and fact.accession_number == evidence.source_accession_number
        and fact.source == evidence.source_system
        and fact.fiscal_year == evidence.fiscal_year
        and fact.fiscal_period == evidence.fiscal_period
        and fact.is_numeric is not False
        and fact.dimensions == evidence.dimensions
        and fact.is_consolidated == evidence.is_consolidated
    )
