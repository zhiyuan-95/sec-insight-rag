"""SQLite persistence for canonical filing chunks and retrieval index state."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.storage.database import initialize_database


@dataclass(frozen=True)
class FilingChunk:
    """One canonical filing-text chunk with source lineage."""

    chunk_id: str
    generation_id: str
    company_id: int
    filing_id: int
    accession_number: str
    section_name: str
    section_title: str
    section_order: int
    chunk_order: int
    text: str
    text_sha256: str
    source_sha256: str
    source_path: Path
    token_count: int
    parser_version: str
    splitter_version: str
    is_active_window: bool = True
    created_at: str = ""


@dataclass(frozen=True)
class RetrievalIndexState:
    """The currently usable retrieval generation for one company."""

    company_id: int
    generation_id: str
    source_fingerprint: str
    parser_version: str
    splitter_version: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    chunk_set_hash: str
    filing_count: int
    chunk_count: int
    artifact_path: Path
    updated_at: str


@dataclass(frozen=True)
class StoredFilingChunk:
    """A stored chunk joined to filing and company metadata."""

    chunk: FilingChunk
    ticker: str
    cik: str
    form_type: str
    filing_date: date
    document_url: str | None
    source_path: Path


class RetrievalRepository:
    """Persist chunks and switch retrieval generations atomically."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        """Create retrieval tables and their dependencies."""
        initialize_database(self.connection)

    def get_state(self, company_id: int) -> RetrievalIndexState | None:
        """Return the current retrieval generation for a company."""
        row = self.connection.execute(
            "SELECT * FROM retrieval_index_state WHERE company_id = ?",
            [company_id],
        ).fetchone()
        return _row_to_state(row) if row is not None else None

    def list_chunks(
        self,
        company_id: int,
        *,
        generation_id: str | None = None,
    ) -> list[StoredFilingChunk]:
        """Return active chunks joined to source filing metadata."""
        params: list[Any] = [company_id]
        generation_clause = ""
        if generation_id is not None:
            generation_clause = " AND fc.generation_id = ?"
            params.append(generation_id)
        rows = self.connection.execute(
            f"""
            SELECT
                fc.*,
                c.ticker,
                c.cik,
                f.form_type,
                f.filing_date,
                f.document_url,
                f.local_path
            FROM filing_chunks AS fc
            JOIN companies AS c ON c.company_id = fc.company_id
            JOIN filings AS f ON f.filing_id = fc.filing_id
            WHERE fc.company_id = ?
              AND fc.is_active_window = 1
              {generation_clause}
            ORDER BY f.filing_date DESC, fc.section_order, fc.chunk_order
            """,
            params,
        ).fetchall()
        return [_row_to_stored_chunk(row) for row in rows]

    def replace_generation(
        self,
        chunks: list[FilingChunk],
        state: RetrievalIndexState,
    ) -> None:
        """Replace canonical chunks and current state in one transaction."""
        if not chunks:
            raise ValueError("A retrieval generation must contain at least one chunk")
        if any(chunk.company_id != state.company_id for chunk in chunks):
            raise ValueError("All chunks must belong to the retrieval state company")
        if any(chunk.generation_id != state.generation_id for chunk in chunks):
            raise ValueError("All chunks must belong to the retrieval state generation")

        rows = [_chunk_to_row(chunk) for chunk in chunks]
        state_row = _state_to_row(state)
        with self.connection:
            self.connection.execute(
                "DELETE FROM filing_chunks WHERE company_id = ?",
                [state.company_id],
            )
            self.connection.executemany(
                """
                INSERT INTO filing_chunks (
                    chunk_id,
                    generation_id,
                    company_id,
                    filing_id,
                    accession_number,
                    section_name,
                    section_title,
                    section_order,
                    chunk_order,
                    text,
                    text_sha256,
                    source_sha256,
                    source_path,
                    token_count,
                    parser_version,
                    splitter_version,
                    is_active_window,
                    created_at
                )
                VALUES (
                    :chunk_id,
                    :generation_id,
                    :company_id,
                    :filing_id,
                    :accession_number,
                    :section_name,
                    :section_title,
                    :section_order,
                    :chunk_order,
                    :text,
                    :text_sha256,
                    :source_sha256,
                    :source_path,
                    :token_count,
                    :parser_version,
                    :splitter_version,
                    :is_active_window,
                    :created_at
                )
                """,
                rows,
            )
            self.connection.execute(
                """
                INSERT INTO retrieval_index_state (
                    company_id,
                    generation_id,
                    source_fingerprint,
                    parser_version,
                    splitter_version,
                    embedding_model,
                    chunk_size,
                    chunk_overlap,
                    chunk_set_hash,
                    filing_count,
                    chunk_count,
                    artifact_path,
                    updated_at
                )
                VALUES (
                    :company_id,
                    :generation_id,
                    :source_fingerprint,
                    :parser_version,
                    :splitter_version,
                    :embedding_model,
                    :chunk_size,
                    :chunk_overlap,
                    :chunk_set_hash,
                    :filing_count,
                    :chunk_count,
                    :artifact_path,
                    :updated_at
                )
                ON CONFLICT(company_id) DO UPDATE SET
                    generation_id = excluded.generation_id,
                    source_fingerprint = excluded.source_fingerprint,
                    parser_version = excluded.parser_version,
                    splitter_version = excluded.splitter_version,
                    embedding_model = excluded.embedding_model,
                    chunk_size = excluded.chunk_size,
                    chunk_overlap = excluded.chunk_overlap,
                    chunk_set_hash = excluded.chunk_set_hash,
                    filing_count = excluded.filing_count,
                    chunk_count = excluded.chunk_count,
                    artifact_path = excluded.artifact_path,
                    updated_at = excluded.updated_at
                """,
                state_row,
            )

    def delete_by_company_id(self, company_id: int) -> tuple[int, int]:
        """Delete retrieval chunks and state for one company."""
        with self.connection:
            chunk_cursor = self.connection.execute(
                "DELETE FROM filing_chunks WHERE company_id = ?",
                [company_id],
            )
            state_cursor = self.connection.execute(
                "DELETE FROM retrieval_index_state WHERE company_id = ?",
                [company_id],
            )
        return chunk_cursor.rowcount, state_cursor.rowcount


def _chunk_to_row(chunk: FilingChunk) -> dict[str, Any]:
    row = asdict(chunk)
    row["source_path"] = str(chunk.source_path)
    row["is_active_window"] = 1 if chunk.is_active_window else 0
    return row


def _state_to_row(state: RetrievalIndexState) -> dict[str, Any]:
    row = asdict(state)
    row["artifact_path"] = str(state.artifact_path)
    return row


def _row_to_state(row: sqlite3.Row) -> RetrievalIndexState:
    return RetrievalIndexState(
        company_id=row["company_id"],
        generation_id=row["generation_id"],
        source_fingerprint=row["source_fingerprint"],
        parser_version=row["parser_version"],
        splitter_version=row["splitter_version"],
        embedding_model=row["embedding_model"],
        chunk_size=row["chunk_size"],
        chunk_overlap=row["chunk_overlap"],
        chunk_set_hash=row["chunk_set_hash"],
        filing_count=row["filing_count"],
        chunk_count=row["chunk_count"],
        artifact_path=Path(row["artifact_path"]),
        updated_at=row["updated_at"],
    )


def _row_to_stored_chunk(row: sqlite3.Row) -> StoredFilingChunk:
    local_path = row["local_path"]
    if not local_path:
        raise ValueError(f"Filing {row['accession_number']} has no local source path")
    chunk = FilingChunk(
        chunk_id=row["chunk_id"],
        generation_id=row["generation_id"],
        company_id=row["company_id"],
        filing_id=row["filing_id"],
        accession_number=row["accession_number"],
        section_name=row["section_name"],
        section_title=row["section_title"],
        section_order=row["section_order"],
        chunk_order=row["chunk_order"],
        text=row["text"],
        text_sha256=row["text_sha256"],
        source_sha256=row["source_sha256"],
        source_path=Path(row["source_path"] or local_path),
        token_count=row["token_count"],
        parser_version=row["parser_version"],
        splitter_version=row["splitter_version"],
        is_active_window=bool(row["is_active_window"]),
        created_at=row["created_at"],
    )
    return StoredFilingChunk(
        chunk=chunk,
        ticker=row["ticker"] or "",
        cik=row["cik"],
        form_type=row["form_type"],
        filing_date=date.fromisoformat(row["filing_date"]),
        document_url=row["document_url"],
        source_path=chunk.source_path,
    )
