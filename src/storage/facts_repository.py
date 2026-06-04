"""SQLite repository for normalized raw XBRL facts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.processing import NormalizedFact
from src.storage.database import initialize_database


@dataclass(frozen=True)
class StoredRawFact:
    """A normalized fact plus its SQLite row identifier."""

    raw_fact_id: int
    fact: NormalizedFact


class RawFactRepository:
    """Persist and retrieve normalized raw XBRL facts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create required database tables."""
        initialize_database(self.connection)

    def upsert_facts(self, facts: list[NormalizedFact]) -> int:
        """Insert or update normalized facts."""
        if not facts:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [_fact_to_row(fact, now) for fact in facts]
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
                source = excluded.source,
                quality_flags = excluded.quality_flags,
                created_at = excluded.created_at
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

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
        return [StoredRawFact(raw_fact_id=row["id"], fact=_row_to_fact(row)) for row in rows]

    def delete_by_cik(self, cik: str) -> int:
        """Delete all raw XBRL facts for one CIK and return deleted row count."""
        cursor = self.connection.execute("DELETE FROM raw_xbrl_facts WHERE cik = ?", [cik])
        self.connection.commit()
        return cursor.rowcount


def _fact_to_row(fact: NormalizedFact, created_at: str) -> dict[str, Any]:
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
    )


def _unique_key(fact: NormalizedFact) -> str:
    parts = [
        fact.cik,
        fact.taxonomy,
        fact.concept,
        fact.unit,
        _date_to_text(fact.start_date),
        _date_to_text(fact.end_date),
        fact.fiscal_year,
        fact.fiscal_period,
        fact.form,
        fact.accession_number,
        fact.frame,
    ]
    return json.dumps(parts, separators=(",", ":"), default=str)


def _date_to_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
