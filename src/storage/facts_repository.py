"""SQLite repository for normalized raw XBRL facts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.processing import NormalizedFact
from src.processing.quality import DUPLICATE_FACT, add_quality_flag
from src.storage.database import initialize_database

_RAW_OBSERVATION_IDENTITY_VERSION = 2


@dataclass(frozen=True)
class RawFactConflictEvidence:
    """One distinct value retained from a quarantined occurrence group."""

    value_raw: object
    value_numeric: Decimal | None
    occurrence_references: tuple[str, ...]


@dataclass(frozen=True)
class StoredRawFact:
    """A normalized fact plus its SQLite row identifier."""

    raw_fact_id: int
    fact: NormalizedFact
    occurrence_count: int = 1
    occurrence_references: tuple[str, ...] = ()
    conflict_evidence: tuple[RawFactConflictEvidence, ...] = ()


@dataclass(frozen=True)
class _PreparedRawFact:
    fact: NormalizedFact
    occurrence_count: int
    occurrence_references: tuple[str, ...]
    conflict_evidence: tuple[RawFactConflictEvidence, ...]


class RawFactRepository:
    """Persist and retrieve normalized raw XBRL facts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)
        self._migrate_raw_observation_identity()

    def _migrate_raw_observation_identity(self) -> None:
        rows = self.connection.execute(
            "SELECT * FROM raw_xbrl_facts ORDER BY id"
        ).fetchall()
        if not any(
            int(row["identity_version"]) < _RAW_OBSERVATION_IDENTITY_VERSION
            for row in rows
        ):
            return

        rows_by_new_key: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            rows_by_new_key.setdefault(_unique_key(_row_to_fact(row)), []).append(
                row
            )
        affected_groups = {
            key: grouped_rows
            for key, grouped_rows in rows_by_new_key.items()
            if any(
                int(row["identity_version"])
                < _RAW_OBSERVATION_IDENTITY_VERSION
                for row in grouped_rows
            )
        }

        with self.connection:
            for grouped_rows in affected_groups.values():
                for row in grouped_rows:
                    self.connection.execute(
                        "UPDATE raw_xbrl_facts SET unique_key = ? WHERE id = ?",
                        [f"raw-observation-migration:{row['id']}", row["id"]],
                    )
            for unique_key, grouped_rows in affected_groups.items():
                prepared = _collapse_observation_groups(
                    [_row_to_fact(row) for row in grouped_rows]
                )[0]
                canonical_raw_fact_id = min(int(row["id"]) for row in grouped_rows)
                duplicate_raw_fact_ids = [
                    int(row["id"])
                    for row in grouped_rows
                    if int(row["id"]) != canonical_raw_fact_id
                ]
                for duplicate_raw_fact_id in duplicate_raw_fact_ids:
                    self._repoint_metric_references(
                        duplicate_raw_fact_id=duplicate_raw_fact_id,
                        canonical_raw_fact_id=canonical_raw_fact_id,
                    )
                    self._replace_indicator_reference(
                        column_name="source_raw_fact_ids",
                        old_id=duplicate_raw_fact_id,
                        new_id=canonical_raw_fact_id,
                    )
                    self.connection.execute(
                        "DELETE FROM raw_xbrl_facts WHERE id = ?",
                        [duplicate_raw_fact_id],
                    )
                self.connection.execute(
                    """
                    UPDATE raw_xbrl_facts
                    SET unique_key = ?,
                        occurrence_count = ?,
                        occurrence_references_json = ?,
                        conflict_evidence_json = ?,
                        quality_flags = ?,
                        identity_version = ?
                    WHERE id = ?
                    """,
                    [
                        unique_key,
                        prepared.occurrence_count,
                        json.dumps(prepared.occurrence_references),
                        _conflict_evidence_to_json(prepared.conflict_evidence),
                        json.dumps(list(prepared.fact.quality_flags)),
                        _RAW_OBSERVATION_IDENTITY_VERSION,
                        canonical_raw_fact_id,
                    ],
                )

    def _repoint_metric_references(
        self,
        *,
        duplicate_raw_fact_id: int,
        canonical_raw_fact_id: int,
    ) -> None:
        duplicate_metrics = self.connection.execute(
            "SELECT * FROM financial_metrics WHERE raw_fact_id = ?",
            [duplicate_raw_fact_id],
        ).fetchall()
        for duplicate_metric in duplicate_metrics:
            canonical_metric = self.connection.execute(
                """
                SELECT metric_id
                FROM financial_metrics
                WHERE company_id IS ?
                  AND metric_name IS ?
                  AND period_type IS ?
                  AND fiscal_year IS ?
                  AND fiscal_period IS ?
                  AND accession_number IS ?
                  AND raw_fact_id = ?
                """,
                [
                    duplicate_metric["company_id"],
                    duplicate_metric["metric_name"],
                    duplicate_metric["period_type"],
                    duplicate_metric["fiscal_year"],
                    duplicate_metric["fiscal_period"],
                    duplicate_metric["accession_number"],
                    canonical_raw_fact_id,
                ],
            ).fetchone()
            if canonical_metric is None:
                self.connection.execute(
                    """
                    UPDATE financial_metrics
                    SET raw_fact_id = ?
                    WHERE metric_id = ?
                    """,
                    [canonical_raw_fact_id, duplicate_metric["metric_id"]],
                )
                continue
            self._replace_indicator_reference(
                column_name="source_metric_ids",
                old_id=int(duplicate_metric["metric_id"]),
                new_id=int(canonical_metric["metric_id"]),
            )
            self.connection.execute(
                "DELETE FROM financial_metrics WHERE metric_id = ?",
                [duplicate_metric["metric_id"]],
            )

    def _replace_indicator_reference(
        self,
        *,
        column_name: str,
        old_id: int,
        new_id: int,
    ) -> None:
        rows = self.connection.execute(
            f"SELECT indicator_id, {column_name} FROM financial_indicators"
        ).fetchall()
        for row in rows:
            existing_ids = [int(value) for value in json.loads(row[column_name])]
            if old_id not in existing_ids:
                continue
            replaced_ids = tuple(
                dict.fromkeys(
                    new_id if value == old_id else value
                    for value in existing_ids
                )
            )
            self.connection.execute(
                f"""
                UPDATE financial_indicators
                SET {column_name} = ?
                WHERE indicator_id = ?
                """,
                [json.dumps(replaced_ids), row["indicator_id"]],
            )

    def upsert_facts(self, facts: list[NormalizedFact]) -> int:
        """Insert or update normalized facts."""
        if not facts:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        prepared_facts = tuple(
            self._merge_with_stored(prepared)
            for prepared in _collapse_observation_groups(facts)
        )
        rows = [_fact_to_row(prepared, now) for prepared in prepared_facts]
        self.connection.executemany(
            """
            INSERT INTO raw_xbrl_facts (
                unique_key,
                cik,
                entity_name,
                taxonomy,
                concept,
                label,
                description,
                unit,
                value_raw,
                value_numeric,
                start_date,
                end_date,
                period_type,
                fiscal_year,
                fiscal_period,
                form,
                filed_date,
                accession_number,
                frame,
                namespace_uri,
                context_id,
                dimensions_json,
                is_consolidated,
                source_document,
                balance,
                is_numeric,
                occurrence_count,
                occurrence_references_json,
                conflict_evidence_json,
                identity_version,
                source,
                quality_flags,
                created_at
            )
            VALUES (
                :unique_key,
                :cik,
                :entity_name,
                :taxonomy,
                :concept,
                :label,
                :description,
                :unit,
                :value_raw,
                :value_numeric,
                :start_date,
                :end_date,
                :period_type,
                :fiscal_year,
                :fiscal_period,
                :form,
                :filed_date,
                :accession_number,
                :frame,
                :namespace_uri,
                :context_id,
                :dimensions_json,
                :is_consolidated,
                :source_document,
                :balance,
                :is_numeric,
                :occurrence_count,
                :occurrence_references_json,
                :conflict_evidence_json,
                :identity_version,
                :source,
                :quality_flags,
                :created_at
            )
            ON CONFLICT(unique_key) DO UPDATE SET
                entity_name = excluded.entity_name,
                label = excluded.label,
                description = excluded.description,
                value_raw = excluded.value_raw,
                value_numeric = excluded.value_numeric,
                period_type = excluded.period_type,
                filed_date = excluded.filed_date,
                namespace_uri = excluded.namespace_uri,
                context_id = excluded.context_id,
                dimensions_json = excluded.dimensions_json,
                is_consolidated = excluded.is_consolidated,
                source_document = excluded.source_document,
                balance = excluded.balance,
                is_numeric = excluded.is_numeric,
                occurrence_count = excluded.occurrence_count,
                occurrence_references_json = excluded.occurrence_references_json,
                conflict_evidence_json = excluded.conflict_evidence_json,
                identity_version = excluded.identity_version,
                source = excluded.source,
                quality_flags = excluded.quality_flags
            """,
            rows,
        )
        self.connection.commit()
        return len(facts)

    def _merge_with_stored(self, prepared: _PreparedRawFact) -> _PreparedRawFact:
        row = self.connection.execute(
            "SELECT * FROM raw_xbrl_facts WHERE unique_key = ?",
            [_unique_key(prepared.fact)],
        ).fetchone()
        if row is None:
            return prepared
        return _merge_prepared_fact(_row_to_stored_raw_fact(row), prepared)

    def list_facts(self, cik: str, concepts: set[str] | None = None) -> list[NormalizedFact]:
        """List stored facts for a CIK, optionally filtering by concept."""
        return [record.fact for record in self.list_fact_records(cik, concepts)]

    def list_fact_records(self, cik: str, concepts: set[str] | None = None) -> list[StoredRawFact]:
        """List stored facts with their raw fact IDs."""
        params: list[Any] = [cik]
        query = "SELECT * FROM raw_xbrl_facts WHERE cik = ?"
        if concepts:
            placeholders = ", ".join("?" for _ in concepts)
            query += f" AND concept IN ({placeholders})"
            params.extend(sorted(concepts))
        query += " ORDER BY concept, end_date, accession_number, unit"
        rows = self.connection.execute(query, params).fetchall()
        return [_row_to_stored_raw_fact(row) for row in rows]

    def list_distinct_concepts(self, cik: str) -> tuple[str, ...]:
        """List distinct raw concept names without loading complete fact rows."""
        rows = self.connection.execute(
            "SELECT DISTINCT concept FROM raw_xbrl_facts WHERE cik = ? ORDER BY concept",
            [cik],
        ).fetchall()
        return tuple(str(row["concept"]) for row in rows if row["concept"])

    def list_distinct_periods(self, cik: str) -> list[tuple[str | None, int | None, str | None]]:
        """List distinct form and fiscal-period values without loading complete facts."""
        rows = self.connection.execute(
            """
            SELECT DISTINCT form, fiscal_year, fiscal_period
            FROM raw_xbrl_facts
            WHERE cik = ?
            """,
            [cik],
        ).fetchall()
        return [(row["form"], row["fiscal_year"], row["fiscal_period"]) for row in rows]

    def has_source_facts(self, cik: str, source: str) -> bool:
        """Return whether a source has already contributed facts for a company."""
        row = self.connection.execute(
            """
            SELECT 1
            FROM raw_xbrl_facts
            WHERE cik = ? AND source = ?
            LIMIT 1
            """,
            [cik, source],
        ).fetchone()
        return row is not None

    def delete_by_cik(self, cik: str) -> int:
        """Delete all raw XBRL facts for one CIK and return deleted row count."""
        cursor = self.connection.execute("DELETE FROM raw_xbrl_facts WHERE cik = ?", [cik])
        self.connection.commit()
        return cursor.rowcount


def _fact_to_row(prepared: _PreparedRawFact, created_at: str) -> dict[str, Any]:
    fact = prepared.fact
    return {
        "unique_key": _unique_key(fact),
        "cik": fact.cik,
        "entity_name": fact.entity_name,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "label": fact.label,
        "description": fact.description,
        "unit": fact.unit,
        "value_raw": json.dumps(fact.value_raw),
        "value_numeric": str(fact.value) if fact.value is not None else None,
        "start_date": _date_to_text(fact.start_date),
        "end_date": _date_to_text(fact.end_date),
        "period_type": fact.period_type,
        "fiscal_year": fact.fiscal_year,
        "fiscal_period": fact.fiscal_period,
        "form": fact.form,
        "filed_date": _date_to_text(fact.filed_date),
        "accession_number": fact.accession_number,
        "frame": fact.frame,
        "namespace_uri": fact.namespace_uri,
        "context_id": fact.context_id,
        "dimensions_json": json.dumps(list(fact.dimensions)),
        "is_consolidated": int(fact.is_consolidated),
        "source_document": fact.source_document,
        "balance": fact.balance,
        "is_numeric": None if fact.is_numeric is None else int(fact.is_numeric),
        "occurrence_count": prepared.occurrence_count,
        "occurrence_references_json": json.dumps(prepared.occurrence_references),
        "conflict_evidence_json": _conflict_evidence_to_json(
            prepared.conflict_evidence
        ),
        "identity_version": _RAW_OBSERVATION_IDENTITY_VERSION,
        "source": fact.source,
        "quality_flags": json.dumps(list(fact.quality_flags)),
        "created_at": created_at,
    }


def _row_to_fact(row: sqlite3.Row) -> NormalizedFact:
    value_numeric = row["value_numeric"]
    return NormalizedFact(
        cik=row["cik"],
        entity_name=row["entity_name"],
        taxonomy=row["taxonomy"],
        concept=row["concept"],
        label=row["label"],
        description=row["description"],
        unit=row["unit"],
        value_raw=json.loads(row["value_raw"]),
        value=Decimal(value_numeric) if value_numeric is not None else None,
        start_date=_text_to_date(row["start_date"]),
        end_date=_text_to_date(row["end_date"]),
        period_type=row["period_type"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        form=row["form"],
        filed_date=_text_to_date(row["filed_date"]),
        accession_number=row["accession_number"],
        frame=row["frame"],
        source=row["source"],
        quality_flags=tuple(json.loads(row["quality_flags"])),
        namespace_uri=row["namespace_uri"],
        context_id=row["context_id"],
        dimensions=tuple(
            (str(dimension), str(member))
            for dimension, member in json.loads(row["dimensions_json"] or "[]")
        ),
        is_consolidated=bool(row["is_consolidated"]),
        source_document=row["source_document"],
        balance=row["balance"],
        is_numeric=(
            None if row["is_numeric"] is None else bool(row["is_numeric"])
        ),
    )


def _row_to_stored_raw_fact(row: sqlite3.Row) -> StoredRawFact:
    return StoredRawFact(
        raw_fact_id=row["id"],
        fact=_row_to_fact(row),
        occurrence_count=int(row["occurrence_count"]),
        occurrence_references=tuple(
            str(reference)
            for reference in json.loads(row["occurrence_references_json"] or "[]")
        ),
        conflict_evidence=_conflict_evidence_from_json(
            row["conflict_evidence_json"]
        ),
    )


def _unique_key(fact: NormalizedFact) -> str:
    parts = [
        fact.cik,
        fact.taxonomy,
        fact.concept,
        fact.unit,
        _date_to_text(fact.start_date),
        _date_to_text(fact.end_date),
        tuple(sorted(fact.dimensions)),
        fact.is_consolidated,
        fact.accession_number,
        fact.source,
    ]
    return json.dumps(parts, separators=(",", ":"), default=str)


def _collapse_observation_groups(
    facts: list[NormalizedFact],
) -> tuple[_PreparedRawFact, ...]:
    grouped: dict[str, list[NormalizedFact]] = {}
    for fact in facts:
        grouped.setdefault(_unique_key(fact), []).append(fact)

    prepared: list[_PreparedRawFact] = []
    for key in sorted(grouped):
        occurrences = grouped[key]
        occurrences_by_value: dict[tuple[str, object], list[NormalizedFact]] = {}
        for fact in occurrences:
            value_identity = _normalized_value_identity(fact.value, fact.value_raw)
            occurrences_by_value.setdefault(value_identity, []).append(fact)
        conflicting = len(occurrences_by_value) > 1
        representative = min(occurrences, key=_representative_sort_key)
        quality_flags = tuple(
            sorted({flag for fact in occurrences for flag in fact.quality_flags})
        )
        if conflicting:
            quality_flags = add_quality_flag(quality_flags, DUPLICATE_FACT)
        elif len(occurrences) > 1:
            quality_flags = tuple(
                flag for flag in quality_flags if flag != DUPLICATE_FACT
            )
        if quality_flags != representative.quality_flags:
            representative = replace(
                representative,
                quality_flags=quality_flags,
            )
        prepared.append(
            _PreparedRawFact(
                fact=representative,
                occurrence_count=len(occurrences),
                occurrence_references=tuple(
                    sorted(
                        {
                            reference
                            for fact in occurrences
                            if (reference := _occurrence_reference(fact)) is not None
                        }
                    )
                ),
                conflict_evidence=(
                    _conflict_evidence(occurrences_by_value)
                    if conflicting
                    else ()
                ),
            )
        )
    return tuple(prepared)


def _merge_prepared_fact(
    stored: StoredRawFact,
    incoming: _PreparedRawFact,
) -> _PreparedRawFact:
    value_evidence: dict[tuple[str, object], RawFactConflictEvidence] = {}
    for item in (*_value_evidence(stored), *_value_evidence(incoming)):
        key = _normalized_value_identity(item.value_numeric, item.value_raw)
        existing = value_evidence.get(key)
        if existing is None:
            value_evidence[key] = item
            continue
        value_evidence[key] = RawFactConflictEvidence(
            value_raw=min(
                (existing.value_raw, item.value_raw),
                key=lambda value: json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
            value_numeric=existing.value_numeric,
            occurrence_references=tuple(
                sorted(
                    set(existing.occurrence_references)
                    | set(item.occurrence_references)
                )
            ),
        )

    merged_evidence = tuple(
        sorted(value_evidence.values(), key=_conflict_evidence_sort_key)
    )
    conflicting = len(merged_evidence) > 1
    representative = min(
        (stored.fact, incoming.fact),
        key=_representative_sort_key,
    )
    quality_flags = tuple(
        sorted(set(stored.fact.quality_flags) | set(incoming.fact.quality_flags))
    )
    if conflicting:
        quality_flags = add_quality_flag(quality_flags, DUPLICATE_FACT)
    elif stored.occurrence_count > 1 or incoming.occurrence_count > 1:
        quality_flags = tuple(
            flag for flag in quality_flags if flag != DUPLICATE_FACT
        )
    if quality_flags != representative.quality_flags:
        representative = replace(representative, quality_flags=quality_flags)

    occurrence_references = tuple(
        sorted(
            set(stored.occurrence_references)
            | set(incoming.occurrence_references)
        )
    )
    occurrence_count = max(
        stored.occurrence_count,
        incoming.occurrence_count,
        len(occurrence_references),
        len(merged_evidence),
    )
    return _PreparedRawFact(
        fact=representative,
        occurrence_count=occurrence_count,
        occurrence_references=occurrence_references,
        conflict_evidence=merged_evidence if conflicting else (),
    )


def _value_evidence(
    observation: StoredRawFact | _PreparedRawFact,
) -> tuple[RawFactConflictEvidence, ...]:
    if observation.conflict_evidence:
        return observation.conflict_evidence
    return (
        RawFactConflictEvidence(
            value_raw=observation.fact.value_raw,
            value_numeric=observation.fact.value,
            occurrence_references=observation.occurrence_references,
        ),
    )


def _occurrence_reference(fact: NormalizedFact) -> str | None:
    parts = (
        ("document", fact.source_document),
        ("context", fact.context_id),
        ("form", fact.form),
        ("fiscal_year", fact.fiscal_year),
        ("fiscal_period", fact.fiscal_period),
        ("frame", fact.frame),
    )
    reference = "|".join(
        f"{name}={value}"
        for name, value in parts
        if value is not None and str(value).strip()
    )
    return reference or None


def _normalized_value_identity(
    value_numeric: Decimal | None,
    value_raw: object,
) -> tuple[str, object]:
    if value_numeric is not None:
        return ("numeric", value_numeric)
    return (
        "raw",
        json.dumps(value_raw, sort_keys=True, separators=(",", ":")),
    )


def _representative_sort_key(fact: NormalizedFact) -> tuple[str, ...]:
    return (
        _value_sort_text(fact),
        fact.source_document or "",
        fact.context_id or "",
        fact.form or "",
        str(fact.fiscal_year or ""),
        fact.fiscal_period or "",
        fact.frame or "",
    )


def _value_sort_text(fact: NormalizedFact) -> str:
    if fact.value is not None:
        return f"numeric:{fact.value}"
    return "raw:" + json.dumps(
        fact.value_raw,
        sort_keys=True,
        separators=(",", ":"),
    )


def _conflict_evidence(
    occurrences_by_value: dict[tuple[str, object], list[NormalizedFact]],
) -> tuple[RawFactConflictEvidence, ...]:
    evidence: list[RawFactConflictEvidence] = []
    for occurrences in occurrences_by_value.values():
        representative = min(occurrences, key=_representative_sort_key)
        evidence.append(
            RawFactConflictEvidence(
                value_raw=representative.value_raw,
                value_numeric=representative.value,
                occurrence_references=tuple(
                    sorted(
                        {
                            reference
                            for fact in occurrences
                            if (reference := _occurrence_reference(fact)) is not None
                        }
                    )
                ),
            )
        )
    return tuple(
        sorted(
            evidence,
            key=_conflict_evidence_sort_key,
        )
    )


def _conflict_evidence_sort_key(
    evidence: RawFactConflictEvidence,
) -> tuple[str, str]:
    return (
        str(evidence.value_numeric) if evidence.value_numeric is not None else "",
        json.dumps(
            evidence.value_raw,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _conflict_evidence_to_json(
    evidence: tuple[RawFactConflictEvidence, ...],
) -> str:
    return json.dumps(
        [
            {
                "value_raw": item.value_raw,
                "value_numeric": (
                    str(item.value_numeric)
                    if item.value_numeric is not None
                    else None
                ),
                "occurrence_references": item.occurrence_references,
            }
            for item in evidence
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _conflict_evidence_from_json(
    payload: str | None,
) -> tuple[RawFactConflictEvidence, ...]:
    rows = json.loads(payload or "[]")
    return tuple(
        RawFactConflictEvidence(
            value_raw=row.get("value_raw"),
            value_numeric=(
                Decimal(str(row["value_numeric"]))
                if row.get("value_numeric") is not None
                else None
            ),
            occurrence_references=tuple(
                str(reference)
                for reference in row.get("occurrence_references", [])
            ),
        )
        for row in rows
    )


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
