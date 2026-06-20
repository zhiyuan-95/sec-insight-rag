"""Build, persist, and query local hybrid filing-retrieval indexes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.core.utils import get_tokenizer
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.retrievers.bm25 import BM25Retriever

from src.retrieval.errors import (
    ActiveFilingsNotFoundError,
    FilingSourceMissingError,
    InvalidRetrievalQueryError,
    RetrievalCompanyNotFoundError,
    RetrievalConfigurationError,
    RetrievalIndexCorruptError,
    RetrievalIndexMismatchError,
    RetrievalIndexNotFoundError,
)
from src.retrieval.models import FilingIndexSummary, IndexSyncResult, RetrievedEvidence
from src.retrieval.parser import PARSER_VERSION, parse_filing_html, sha256_file
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FilingChunk,
    FilingRecord,
    FilingRepository,
    RetrievalIndexState,
    RetrievalRepository,
    StoredFilingChunk,
    connect_sqlite,
)

if TYPE_CHECKING:
    from src.config import Settings

INDEX_ID = "filing_evidence"
CANDIDATE_TOP_K = 20
DEFAULT_TOP_K = 8
MAX_TOP_K = 20
MAX_QUERY_CHARACTERS = 1000
RRF_CONSTANT = 60.0
MANIFEST_VERSION = 1


def sync_company_retrieval_index(
    ticker: str,
    settings: Settings,
    *,
    force_rebuild: bool = False,
) -> IndexSyncResult:
    """Build or reuse a complete local retrieval generation for one company."""
    started = time.perf_counter()
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise RetrievalCompanyNotFoundError("Ticker is required")

    knowledge_dir = _prepare_knowledge_storage(settings.knowledge_storage_dir)
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        retrieval_repository = RetrievalRepository(connection)
        retrieval_repository.initialize()

        company = company_repository.get_by_ticker(normalized_ticker)
        if company is None or company.company_id is None:
            raise RetrievalCompanyNotFoundError(
                f"No locally ingested company was found for ticker {normalized_ticker}"
            )
        filings = filing_repository.list_filings(
            company.company_id,
            forms={"10-K", "10-Q"},
            active_only=True,
        )
        if not filings:
            raise ActiveFilingsNotFoundError(
                f"No active 10-K or 10-Q filings are stored for {normalized_ticker}"
            )

        resolved_sources = [
            (filing, _resolve_filing_path(filing, company, settings))
            for filing in filings
        ]
        source_hashes = {
            filing.accession_number: sha256_file(path)
            for filing, path in resolved_sources
        }
        splitter_version = _splitter_version(settings)
        source_fingerprint = _source_fingerprint(
            resolved_sources=resolved_sources,
            source_hashes=source_hashes,
            splitter_version=splitter_version,
            settings=settings,
        )
        current_state = retrieval_repository.get_state(company.company_id)
        reuse_warning: str | None = None
        if (
            not force_rebuild
            and current_state is not None
            and current_state.source_fingerprint == source_fingerprint
        ):
            try:
                stored_chunks = retrieval_repository.list_chunks(
                    company.company_id,
                    generation_id=current_state.generation_id,
                )
                _validate_generation(current_state, stored_chunks)
                summaries = _summaries_from_stored_chunks(stored_chunks)
                return IndexSyncResult(
                    ticker=normalized_ticker,
                    cik=company.cik,
                    company_id=company.company_id,
                    status="reused",
                    generation_id=current_state.generation_id,
                    artifact_path=current_state.artifact_path,
                    filing_count=current_state.filing_count,
                    chunk_count=current_state.chunk_count,
                    filing_summaries=summaries,
                    warnings=(),
                    elapsed_seconds=time.perf_counter() - started,
                )
            except (RetrievalIndexMismatchError, RetrievalIndexCorruptError) as exc:
                reuse_warning = f"Current generation could not be reused and was rebuilt: {exc}"

        generation_id = _generation_id(source_fingerprint)
        generation_path = (
            knowledge_dir / company.cik / "generations" / generation_id
        ).resolve()
        chunks, summaries, build_warnings = _build_chunks(
            company=company,
            resolved_sources=resolved_sources,
            source_hashes=source_hashes,
            generation_id=generation_id,
            splitter_version=splitter_version,
            settings=settings,
        )
        chunk_set_hash = _chunk_set_hash(chunks)
        state = RetrievalIndexState(
            company_id=company.company_id,
            generation_id=generation_id,
            source_fingerprint=source_fingerprint,
            parser_version=PARSER_VERSION,
            splitter_version=splitter_version,
            embedding_model=settings.retrieval_embedding_model,
            chunk_size=settings.retrieval_chunk_size,
            chunk_overlap=settings.retrieval_chunk_overlap,
            chunk_set_hash=chunk_set_hash,
            filing_count=len(filings),
            chunk_count=len(chunks),
            artifact_path=generation_path,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            _build_index_artifacts(
                chunks=chunks,
                summaries=summaries,
                state=state,
                settings=settings,
                knowledge_dir=knowledge_dir,
            )
            retrieval_repository.replace_generation(chunks, state)
        except Exception:
            _remove_generation_if_present(generation_path)
            raise

        cleanup_warnings = _cleanup_old_generations(
            knowledge_dir=knowledge_dir,
            cik=company.cik,
            current_generation=generation_id,
        )
        warnings = list(build_warnings)
        if reuse_warning:
            warnings.insert(0, reuse_warning)
        warnings.extend(cleanup_warnings)
        return IndexSyncResult(
            ticker=normalized_ticker,
            cik=company.cik,
            company_id=company.company_id,
            status="built",
            generation_id=generation_id,
            artifact_path=generation_path,
            filing_count=len(filings),
            chunk_count=len(chunks),
            filing_summaries=tuple(summaries),
            warnings=tuple(warnings),
            elapsed_seconds=time.perf_counter() - started,
        )


def retrieve_filing_evidence(
    ticker: str,
    query: str,
    settings: Settings,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[RetrievedEvidence, ...]:
    """Retrieve locally indexed filing evidence with vector and BM25 fusion."""
    normalized_ticker = ticker.strip().upper()
    normalized_query = " ".join(query.split())
    if not normalized_query:
        raise InvalidRetrievalQueryError("Retrieval query must not be empty")
    if len(normalized_query) > MAX_QUERY_CHARACTERS:
        raise InvalidRetrievalQueryError(
            f"Retrieval query exceeds the {MAX_QUERY_CHARACTERS}-character limit"
        )
    if top_k < 1 or top_k > MAX_TOP_K:
        raise InvalidRetrievalQueryError(f"top_k must be between 1 and {MAX_TOP_K}")

    knowledge_dir = _prepare_knowledge_storage(settings.knowledge_storage_dir)
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        retrieval_repository = RetrievalRepository(connection)
        retrieval_repository.initialize()
        company = company_repository.get_by_ticker(normalized_ticker)
        if company is None or company.company_id is None:
            raise RetrievalCompanyNotFoundError(
                f"No locally ingested company was found for ticker {normalized_ticker}"
            )
        state = retrieval_repository.get_state(company.company_id)
        if state is None:
            raise RetrievalIndexNotFoundError(
                f"No retrieval index exists for {normalized_ticker}; run index synchronization first"
            )
        chunks = retrieval_repository.list_chunks(
            company.company_id,
            generation_id=state.generation_id,
        )
        _validate_generation(state, chunks)
        node_by_id = {stored.chunk.chunk_id: stored for stored in chunks}

    try:
        vector_retriever, bm25_retriever = _load_retrievers(
            str(state.artifact_path),
            settings.retrieval_embedding_model,
            str(knowledge_dir / "model_cache" / "fastembed"),
        )
        vector_results = vector_retriever.retrieve(normalized_query)
        bm25_results = bm25_retriever.retrieve(normalized_query)
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
        raise RetrievalIndexCorruptError(
            f"Could not load retrieval generation {state.generation_id}: {exc}"
        ) from exc

    fused = _reciprocal_rank_fusion(vector_results, bm25_results)
    evidence: list[RetrievedEvidence] = []
    for rank, item in enumerate(fused[:top_k], start=1):
        stored = node_by_id.get(item["chunk_id"])
        if stored is None:
            raise RetrievalIndexMismatchError(
                f"Retrieved chunk {item['chunk_id']} is not present in canonical SQLite storage"
            )
        chunk = stored.chunk
        evidence.append(
            RetrievedEvidence(
                rank=rank,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                ticker=stored.ticker,
                cik=stored.cik,
                form_type=stored.form_type,
                filing_date=stored.filing_date,
                accession_number=chunk.accession_number,
                section_name=chunk.section_name,
                section_title=chunk.section_title,
                source_url=stored.document_url,
                source_path=stored.source_path,
                text_sha256=chunk.text_sha256,
                vector_score=item["vector_score"],
                vector_rank=item["vector_rank"],
                bm25_score=item["bm25_score"],
                bm25_rank=item["bm25_rank"],
                fused_score=item["fused_score"],
            )
        )
    return tuple(evidence)


def delete_company_retrieval_artifacts(
    settings: Settings,
    cik: str,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Delete one company's rebuildable retrieval artifact directory."""
    company_dir = (settings.knowledge_storage_dir / cik).resolve()
    knowledge_dir = settings.knowledge_storage_dir.resolve()
    if company_dir.parent != knowledge_dir:
        return (), (company_dir,)
    if not company_dir.exists():
        return (), ()
    try:
        shutil.rmtree(company_dir)
    except OSError:
        return (), (company_dir,)
    return (company_dir,), ()


def _build_chunks(
    *,
    company: CompanyRecord,
    resolved_sources: list[tuple[FilingRecord, Path]],
    source_hashes: dict[str, str],
    generation_id: str,
    splitter_version: str,
    settings: Settings,
) -> tuple[list[FilingChunk], list[FilingIndexSummary], list[str]]:
    if company.company_id is None:
        raise RetrievalCompanyNotFoundError("Stored company is missing company_id")
    splitter = SentenceSplitter(
        chunk_size=settings.retrieval_chunk_size,
        chunk_overlap=settings.retrieval_chunk_overlap,
    )
    tokenizer = get_tokenizer()
    now = datetime.now(timezone.utc).isoformat()
    chunks: list[FilingChunk] = []
    summaries: list[FilingIndexSummary] = []
    warnings: list[str] = []

    for filing, source_path in resolved_sources:
        if filing.filing_id is None:
            raise RetrievalConfigurationError(
                f"Filing {filing.accession_number} is missing its stored filing_id"
            )
        parsed = parse_filing_html(source_path, filing.form_type)
        filing_chunks: list[FilingChunk] = []
        for section in parsed.sections:
            split_texts = [text.strip() for text in splitter.split_text(section.text) if text.strip()]
            for chunk_order, text in enumerate(split_texts):
                text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                chunk_id = _chunk_id(
                    accession_number=filing.accession_number,
                    source_sha256=parsed.source_sha256,
                    section_name=section.name,
                    chunk_order=chunk_order,
                    splitter_version=splitter_version,
                    text_sha256=text_sha256,
                )
                filing_chunks.append(
                    FilingChunk(
                        chunk_id=chunk_id,
                        generation_id=generation_id,
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number=filing.accession_number,
                        section_name=section.name,
                        section_title=section.title,
                        section_order=section.order,
                        chunk_order=chunk_order,
                        text=text,
                        text_sha256=text_sha256,
                        source_sha256=parsed.source_sha256,
                        source_path=source_path,
                        token_count=len(tokenizer(text)),
                        parser_version=PARSER_VERSION,
                        splitter_version=splitter_version,
                        created_at=now,
                    )
                )
        if not filing_chunks:
            raise RetrievalConfigurationError(
                f"Filing {filing.accession_number} produced no chunks"
            )
        if parsed.source_sha256 != source_hashes[filing.accession_number]:
            raise RetrievalIndexMismatchError(
                f"Filing {filing.accession_number} changed while its index was being built"
            )
        chunks.extend(filing_chunks)
        filing_warnings = tuple(
            f"{filing.accession_number}: {warning}" for warning in parsed.warnings
        )
        warnings.extend(filing_warnings)
        summaries.append(
            FilingIndexSummary(
                accession_number=filing.accession_number,
                form_type=filing.form_type,
                filing_date=filing.filing_date,
                source_path=source_path,
                source_sha256=parsed.source_sha256,
                section_names=tuple(section.name for section in parsed.sections),
                chunk_count=len(filing_chunks),
                used_fallback=parsed.used_fallback,
                warnings=filing_warnings,
            )
        )
    return chunks, summaries, warnings


def _build_index_artifacts(
    *,
    chunks: list[FilingChunk],
    summaries: list[FilingIndexSummary],
    state: RetrievalIndexState,
    settings: Settings,
    knowledge_dir: Path,
) -> None:
    path = state.artifact_path
    if path.exists():
        raise RetrievalConfigurationError(f"Retrieval generation already exists: {path}")
    path.mkdir(parents=True, exist_ok=False)
    summary_by_accession = {
        summary.accession_number: summary for summary in summaries
    }
    nodes = [_chunk_to_node(chunk, summary_by_accession) for chunk in chunks]
    embed_model = _embedding_model(settings, knowledge_dir)
    try:
        vector_index = VectorStoreIndex(
            nodes,
            embed_model=embed_model,
            insert_batch_size=64,
            show_progress=False,
        )
        vector_index.set_index_id(INDEX_ID)
        vector_index.storage_context.persist(persist_dir=str(path / "vector"))
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes,
            similarity_top_k=CANDIDATE_TOP_K,
        )
        bm25_retriever.persist(str(path / "bm25"))
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "generation_id": state.generation_id,
            "source_fingerprint": state.source_fingerprint,
            "parser_version": state.parser_version,
            "splitter_version": state.splitter_version,
            "embedding_model": state.embedding_model,
            "chunk_size": state.chunk_size,
            "chunk_overlap": state.chunk_overlap,
            "chunk_set_hash": state.chunk_set_hash,
            "filing_count": state.filing_count,
            "chunk_count": state.chunk_count,
            "created_at": state.updated_at,
        }
        (path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _require_complete_artifact_set(path)
    except Exception as exc:
        raise RetrievalConfigurationError(
            f"Could not build retrieval generation {state.generation_id}: {exc}"
        ) from exc


def _embedding_model(settings: Settings, knowledge_dir: Path) -> FastEmbedEmbedding:
    cache_dir = knowledge_dir / "model_cache" / "fastembed"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return _cached_embedding_model(
        settings.retrieval_embedding_model,
        str(cache_dir),
    )


@lru_cache(maxsize=4)
def _load_retrievers(
    artifact_path: str,
    model_name: str,
    cache_dir: str,
) -> tuple[Any, BM25Retriever]:
    path = Path(artifact_path)
    embed_model = _cached_embedding_model(model_name, cache_dir)
    storage_context = StorageContext.from_defaults(
        persist_dir=str(path / "vector")
    )
    vector_index = load_index_from_storage(
        storage_context,
        index_id=INDEX_ID,
        embed_model=embed_model,
    )
    vector_retriever = vector_index.as_retriever(
        similarity_top_k=CANDIDATE_TOP_K
    )
    bm25_retriever = BM25Retriever.from_persist_dir(str(path / "bm25"))
    return vector_retriever, bm25_retriever


@lru_cache(maxsize=4)
def _cached_embedding_model(
    model_name: str,
    cache_dir: str,
) -> FastEmbedEmbedding:
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    try:
        return FastEmbedEmbedding(
            model_name=model_name,
            cache_dir=cache_dir,
            doc_embed_type="passage",
            embed_batch_size=256,
        )
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        raise RetrievalConfigurationError(
            f"Could not initialize local embedding model {model_name}: {exc}"
        ) from exc


def _validate_generation(
    state: RetrievalIndexState,
    chunks: list[StoredFilingChunk],
) -> None:
    if len(chunks) != state.chunk_count:
        raise RetrievalIndexMismatchError(
            f"SQLite has {len(chunks)} chunks but state expects {state.chunk_count}"
        )
    if any(chunk.chunk.generation_id != state.generation_id for chunk in chunks):
        raise RetrievalIndexMismatchError("SQLite contains chunks from a different generation")
    chunk_hash = _stored_chunk_set_hash(chunks)
    if chunk_hash != state.chunk_set_hash:
        raise RetrievalIndexMismatchError("SQLite chunk hash does not match retrieval state")
    manifest_path = state.artifact_path / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetrievalIndexCorruptError(f"Could not read {manifest_path}: {exc}") from exc
    expected = {
        "generation_id": state.generation_id,
        "source_fingerprint": state.source_fingerprint,
        "chunk_set_hash": state.chunk_set_hash,
        "chunk_count": state.chunk_count,
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise RetrievalIndexMismatchError(
                f"Manifest {key} does not match retrieval state"
            )
    if not (state.artifact_path / "vector").is_dir() or not (
        state.artifact_path / "bm25"
    ).is_dir():
        raise RetrievalIndexCorruptError(
            f"Generation {state.generation_id} is missing vector or BM25 artifacts"
        )
    _require_complete_artifact_set(state.artifact_path)


def _reciprocal_rank_fusion(vector_results: list[Any], bm25_results: list[Any]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for component, results in (("vector", vector_results), ("bm25", bm25_results)):
        for index, result in enumerate(results):
            chunk_id = result.node.node_id
            item = combined.setdefault(
                chunk_id,
                {
                    "chunk_id": chunk_id,
                    "vector_score": None,
                    "vector_rank": None,
                    "bm25_score": None,
                    "bm25_rank": None,
                    "fused_score": 0.0,
                },
            )
            rank = index + 1
            item[f"{component}_score"] = float(result.score) if result.score is not None else None
            item[f"{component}_rank"] = rank
            item["fused_score"] += 1.0 / (RRF_CONSTANT + index)
    return sorted(
        combined.values(),
        key=lambda item: (-item["fused_score"], item["chunk_id"]),
    )


def _chunk_to_node(
    chunk: FilingChunk,
    summary_by_accession: dict[str, FilingIndexSummary],
) -> TextNode:
    summary = summary_by_accession[chunk.accession_number]
    metadata = {
        "accession_number": chunk.accession_number,
        "form_type": summary.form_type,
        "filing_date": summary.filing_date.isoformat(),
        "section_name": chunk.section_name,
        "section_title": chunk.section_title,
        "source_path": str(summary.source_path),
        "text_sha256": chunk.text_sha256,
    }
    excluded = [
        "accession_number",
        "form_type",
        "filing_date",
        "source_path",
        "text_sha256",
    ]
    return TextNode(
        id_=chunk.chunk_id,
        text=chunk.text,
        metadata=metadata,
        excluded_embed_metadata_keys=excluded,
        excluded_llm_metadata_keys=list(metadata),
    )
def _summaries_from_stored_chunks(
    chunks: list[StoredFilingChunk],
) -> tuple[FilingIndexSummary, ...]:
    grouped: dict[str, list[StoredFilingChunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.chunk.accession_number].append(chunk)
    summaries = []
    for accession, group in grouped.items():
        first = group[0]
        section_names = tuple(dict.fromkeys(item.chunk.section_name for item in group))
        summaries.append(
            FilingIndexSummary(
                accession_number=accession,
                form_type=first.form_type,
                filing_date=first.filing_date,
                source_path=first.source_path,
                source_sha256=first.chunk.source_sha256,
                section_names=section_names,
                chunk_count=len(group),
                used_fallback="unclassified_full_filing" in section_names,
            )
        )
    return tuple(sorted(summaries, key=lambda item: item.filing_date, reverse=True))


def _resolve_filing_path(
    filing: FilingRecord,
    company: CompanyRecord,
    settings: Settings,
) -> Path:
    if filing.local_path is None:
        raise FilingSourceMissingError(
            f"Active filing {filing.accession_number} has no local_path"
        )
    recorded = filing.local_path.expanduser()
    candidates = [recorded]
    if not recorded.is_absolute():
        candidates.insert(0, Path.cwd() / recorded)
    candidates.extend(
        [
            settings.stock_filings_base_dir
            / company.cik
            / filing.accession_number
            / recorded.name,
            settings.stock_filings_base_dir / company.cik / recorded.name,
            settings.stock_filings_base_dir / recorded.name,
        ]
    )
    allowed_roots = {
        Path.cwd().resolve(),
        settings.stock_filings_base_dir.expanduser().resolve(),
        settings.stock_storage_base_dir.expanduser().resolve(),
        settings.stock_sql_db_path.expanduser().resolve().parent,
    }
    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.is_file():
            continue
        if any(_is_relative_to(resolved, root) for root in allowed_roots):
            return resolved
    raise FilingSourceMissingError(
        f"Active filing {filing.accession_number} is missing or outside configured storage roots; "
        f"recorded path: {filing.local_path}"
    )


def _prepare_knowledge_storage(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        probe = resolved / ".write-probe"
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError as exc:
        raise RetrievalConfigurationError(
            f"Knowledge storage directory is not writable: {resolved}: {exc}"
        ) from exc
    return resolved


def _source_fingerprint(
    *,
    resolved_sources: list[tuple[FilingRecord, Path]],
    source_hashes: dict[str, str],
    splitter_version: str,
    settings: Settings,
) -> str:
    lines = [
        f"parser={PARSER_VERSION}",
        f"splitter={splitter_version}",
        f"embedding={settings.retrieval_embedding_model}",
    ]
    lines.extend(
        f"{filing.accession_number}|{source_hashes[filing.accession_number]}"
        for filing, _ in sorted(resolved_sources, key=lambda item: item[0].accession_number)
    )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _splitter_version(settings: Settings) -> str:
    return f"sentence-v1-size{settings.retrieval_chunk_size}-overlap{settings.retrieval_chunk_overlap}"


def _generation_id(source_fingerprint: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{source_fingerprint[:12]}"


def _chunk_id(
    *,
    accession_number: str,
    source_sha256: str,
    section_name: str,
    chunk_order: int,
    splitter_version: str,
    text_sha256: str,
) -> str:
    value = "|".join(
        [
            accession_number,
            source_sha256,
            section_name,
            str(chunk_order),
            PARSER_VERSION,
            splitter_version,
            text_sha256,
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _chunk_set_hash(chunks: list[FilingChunk]) -> str:
    values = sorted(f"{chunk.chunk_id}|{chunk.text_sha256}" for chunk in chunks)
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _stored_chunk_set_hash(chunks: list[StoredFilingChunk]) -> str:
    values = sorted(
        f"{stored.chunk.chunk_id}|{stored.chunk.text_sha256}" for stored in chunks
    )
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _cleanup_old_generations(
    *,
    knowledge_dir: Path,
    cik: str,
    current_generation: str,
) -> list[str]:
    generations_dir = (knowledge_dir / cik / "generations").resolve()
    if not generations_dir.is_dir():
        return []
    warnings: list[str] = []
    for child in generations_dir.iterdir():
        if child.name == current_generation or not child.is_dir():
            continue
        if child.parent != generations_dir:
            warnings.append(f"Skipped unsafe generation cleanup path: {child}")
            continue
        try:
            _remove_tree(child)
        except OSError as exc:
            warnings.append(f"Could not remove obsolete generation {child}: {exc}")
    return warnings


def _remove_generation_if_present(path: Path) -> None:
    if path.is_dir():
        try:
            _remove_tree(path)
        except OSError:
            pass


def _require_complete_artifact_set(path: Path) -> None:
    required = (
        path / "manifest.json",
        path / "vector" / "docstore.json",
        path / "vector" / "index_store.json",
        path / "vector" / "default__vector_store.json",
        path / "bm25" / "retriever.json",
        path / "bm25" / "params.index.json",
        path / "bm25" / "corpus.jsonl",
    )
    missing = [str(candidate) for candidate in required if not candidate.is_file()]
    if missing:
        raise RetrievalIndexCorruptError(
            "Retrieval generation is incomplete; missing: " + ", ".join(missing)
        )


def _remove_tree(path: Path) -> None:
    def _clear_read_only(function: Any, target: str, _: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=_clear_read_only)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
