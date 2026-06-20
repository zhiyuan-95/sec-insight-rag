"""Data contracts for filing parsing, index synchronization, and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ParsedSection:
    """A canonical section extracted from one SEC filing."""

    name: str
    title: str
    order: int
    text: str


@dataclass(frozen=True)
class ParsedFiling:
    """Visible filing text split into canonical SEC sections."""

    source_sha256: str
    sections: tuple[ParsedSection, ...]
    warnings: tuple[str, ...] = ()
    used_fallback: bool = False


@dataclass(frozen=True)
class FilingIndexSummary:
    """Human-inspectable chunking summary for one filing."""

    accession_number: str
    form_type: str
    filing_date: date
    source_path: Path
    source_sha256: str
    section_names: tuple[str, ...]
    chunk_count: int
    used_fallback: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndexSyncResult:
    """Summary of a company retrieval index build or reuse."""

    ticker: str
    cik: str
    company_id: int
    status: str
    generation_id: str
    artifact_path: Path
    filing_count: int
    chunk_count: int
    filing_summaries: tuple[FilingIndexSummary, ...]
    warnings: tuple[str, ...]
    elapsed_seconds: float


@dataclass(frozen=True)
class RetrievedEvidence:
    """One ranked filing chunk with complete retrieval and source lineage."""

    rank: int
    chunk_id: str
    text: str
    ticker: str
    cik: str
    form_type: str
    filing_date: date
    accession_number: str
    section_name: str
    section_title: str
    source_url: str | None
    source_path: Path
    text_sha256: str
    vector_score: float | None
    vector_rank: int | None
    bm25_score: float | None
    bm25_rank: int | None
    fused_score: float
