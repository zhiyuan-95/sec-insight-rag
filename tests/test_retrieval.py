import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.retrieval import service as retrieval_service
from src.retrieval.errors import (
    EmptyFilingTextError,
    InvalidRetrievalQueryError,
    RetrievalIndexMismatchError,
)
from src.retrieval.models import FilingIndexSummary
from src.retrieval.parser import parse_filing_html, sha256_file
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FilingChunk,
    FilingRecord,
    FilingRepository,
    RetrievalIndexState,
    RetrievalRepository,
    connect_sqlite,
)


def test_parser_extracts_visible_form_sections_and_removes_hidden_content(tmp_path) -> None:
    filing_path = tmp_path / "filing.htm"
    business = "Business operations and product information. " * 8
    risks = "Risk factors include competition and operational uncertainty. " * 8
    filing_path.write_text(
        f"""
        <html><body>
          <script>secret script text</script>
          <div style="display:none">hidden filing text</div>
          <h2>Item 1. Business</h2><p>{business}</p>
          <h2>Item 1A. Risk Factors</h2><p>{risks}</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    parsed = parse_filing_html(filing_path, "10-k")

    assert parsed.used_fallback is False
    assert [section.name for section in parsed.sections] == ["business", "risk_factors"]
    assert "secret script text" not in " ".join(section.text for section in parsed.sections)
    assert "hidden filing text" not in " ".join(section.text for section in parsed.sections)
    assert parsed.source_sha256 == sha256_file(filing_path)


def test_parser_falls_back_when_sec_item_headings_are_unavailable(tmp_path) -> None:
    filing_path = tmp_path / "filing.htm"
    filing_path.write_text(
        "<html><body><p>Visible filing narrative without item headings. "
        + "Additional filing detail. " * 10
        + "</p></body></html>",
        encoding="utf-8",
    )

    parsed = parse_filing_html(filing_path, "10-Q")

    assert parsed.used_fallback is True
    assert parsed.sections[0].name == "unclassified_full_filing"
    assert "No reliable SEC item headings" in parsed.warnings[0]


def test_parser_rejects_filing_without_visible_text(tmp_path) -> None:
    filing_path = tmp_path / "empty.htm"
    filing_path.write_text(
        "<html><body><script>only hidden content</script></body></html>",
        encoding="utf-8",
    )

    with pytest.raises(EmptyFilingTextError):
        parse_filing_html(filing_path, "10-K")


def test_retrieval_repository_replaces_generation_and_round_trips_lineage(tmp_path) -> None:
    db_path = tmp_path / "retrieval.db"
    source_path = tmp_path / "filing.htm"
    source_path.write_text("filing", encoding="utf-8")
    with connect_sqlite(db_path) as connection:
        company_id, filing_id = _seed_company_and_filing(connection, source_path)
        chunk = _chunk(company_id, filing_id, source_path, "generation-1")
        state = _state(company_id, tmp_path / "generation-1", chunk)
        repository = RetrievalRepository(connection)

        repository.replace_generation([chunk], state)

        assert repository.get_state(company_id) == state
        stored = repository.list_chunks(company_id, generation_id="generation-1")
        assert len(stored) == 1
        assert stored[0].chunk == chunk
        assert stored[0].ticker == "TEST"
        assert stored[0].form_type == "10-K"
        assert stored[0].source_path == source_path


def test_retrieval_repository_rolls_back_when_new_generation_is_invalid(tmp_path) -> None:
    db_path = tmp_path / "retrieval.db"
    source_path = tmp_path / "filing.htm"
    source_path.write_text("filing", encoding="utf-8")
    with connect_sqlite(db_path) as connection:
        company_id, filing_id = _seed_company_and_filing(connection, source_path)
        repository = RetrievalRepository(connection)
        old_chunk = _chunk(company_id, filing_id, source_path, "generation-1")
        old_state = _state(company_id, tmp_path / "generation-1", old_chunk)
        repository.replace_generation([old_chunk], old_state)
        invalid_chunk = _chunk(company_id, 999999, source_path, "generation-2")
        invalid_state = _state(company_id, tmp_path / "generation-2", invalid_chunk)

        with pytest.raises(sqlite3.IntegrityError):
            repository.replace_generation([invalid_chunk], invalid_state)

        assert repository.get_state(company_id) == old_state
        assert [row.chunk for row in repository.list_chunks(company_id)] == [old_chunk]


def test_reciprocal_rank_fusion_preserves_component_scores_and_rewards_overlap() -> None:
    vector_results = [_result("a", 0.9), _result("b", 0.8)]
    bm25_results = [_result("b", 5.0), _result("c", 4.0)]

    fused = retrieval_service._reciprocal_rank_fusion(vector_results, bm25_results)

    assert [item["chunk_id"] for item in fused] == ["b", "a", "c"]
    assert fused[0]["vector_rank"] == 2
    assert fused[0]["bm25_rank"] == 1
    assert fused[0]["vector_score"] == 0.8
    assert fused[0]["bm25_score"] == 5.0


@pytest.mark.parametrize(
    ("query", "top_k"),
    [("", 8), ("   ", 8), ("valid", 0), ("valid", 21), ("x" * 1001, 8)],
)
def test_retrieve_rejects_invalid_queries_before_storage_access(
    tmp_path,
    query: str,
    top_k: int,
) -> None:
    with pytest.raises(InvalidRetrievalQueryError):
        retrieval_service.retrieve_filing_evidence(
            "TEST",
            query,
            _settings(tmp_path),
            top_k=top_k,
        )


def test_retrieve_returns_ranked_evidence_with_complete_sqlite_lineage(
    tmp_path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    source_path = settings.stock_filings_base_dir / "filing.htm"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("filing", encoding="utf-8")
    artifact_path = settings.knowledge_storage_dir / "generation-1"
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_id, filing_id = _seed_company_and_filing(connection, source_path)
        chunk = _chunk(company_id, filing_id, source_path, "generation-1")
        state = _state(company_id, artifact_path, chunk)
        RetrievalRepository(connection).replace_generation([chunk], state)
    _write_complete_artifacts(state)
    monkeypatch.setattr(
        retrieval_service,
        "_load_retrievers",
        lambda *_: (
            _FakeRetriever([_result(chunk.chunk_id, 0.91)]),
            _FakeRetriever([_result(chunk.chunk_id, 7.5)]),
        ),
    )

    evidence = retrieval_service.retrieve_filing_evidence(
        " test ",
        "  revenue   risk  ",
        settings,
        top_k=1,
    )

    assert len(evidence) == 1
    item = evidence[0]
    assert item.rank == 1
    assert item.chunk_id == chunk.chunk_id
    assert item.text == chunk.text
    assert item.ticker == "TEST"
    assert item.cik == "0000000001"
    assert item.accession_number == "test-accession"
    assert item.source_url == "https://example.test/filing.htm"
    assert item.source_path == source_path
    assert item.vector_score == 0.91
    assert item.bm25_score == 7.5


def test_retrieve_rejects_manifest_that_disagrees_with_sqlite(tmp_path) -> None:
    settings = _settings(tmp_path)
    source_path = settings.stock_filings_base_dir / "filing.htm"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("filing", encoding="utf-8")
    artifact_path = settings.knowledge_storage_dir / "generation-1"
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_id, filing_id = _seed_company_and_filing(connection, source_path)
        chunk = _chunk(company_id, filing_id, source_path, "generation-1")
        state = _state(company_id, artifact_path, chunk)
        RetrievalRepository(connection).replace_generation([chunk], state)
    _write_complete_artifacts(state)
    manifest_path = artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["chunk_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RetrievalIndexMismatchError, match="Manifest chunk_count"):
        retrieval_service.retrieve_filing_evidence("TEST", "query", settings)


def test_sync_builds_reuses_and_preserves_previous_generation_on_build_failure(
    tmp_path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    source_path = settings.stock_filings_base_dir / "filing.htm"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("<html><body>filing source</body></html>", encoding="utf-8")
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        _seed_company_and_filing(connection, source_path)
    build_calls: list[str] = []

    def fake_build_chunks(**kwargs):
        filing = kwargs["resolved_sources"][0][0]
        company = kwargs["company"]
        generation_id = kwargs["generation_id"]
        chunk = _chunk(company.company_id, filing.filing_id, source_path, generation_id)
        summary = FilingIndexSummary(
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            source_path=source_path,
            source_sha256=kwargs["source_hashes"][filing.accession_number],
            section_names=("business",),
            chunk_count=1,
            used_fallback=False,
        )
        return [chunk], [summary], []

    def fake_build_artifacts(**kwargs):
        state = kwargs["state"]
        build_calls.append(state.generation_id)
        _write_complete_artifacts(state)

    monkeypatch.setattr(retrieval_service, "_build_chunks", fake_build_chunks)
    monkeypatch.setattr(retrieval_service, "_build_index_artifacts", fake_build_artifacts)

    built = retrieval_service.sync_company_retrieval_index("TEST", settings)
    reused = retrieval_service.sync_company_retrieval_index("TEST", settings)

    assert built.status == "built"
    assert reused.status == "reused"
    assert reused.generation_id == built.generation_id
    assert build_calls == [built.generation_id]

    def fail_build(**kwargs):
        raise RuntimeError("simulated index failure")

    monkeypatch.setattr(retrieval_service, "_build_index_artifacts", fail_build)
    with pytest.raises(RuntimeError, match="simulated index failure"):
        retrieval_service.sync_company_retrieval_index(
            "TEST",
            settings,
            force_rebuild=True,
        )

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        repository = RetrievalRepository(connection)
        assert repository.get_state(built.company_id).generation_id == built.generation_id
        assert len(repository.list_chunks(built.company_id)) == 1


class _FakeRetriever:
    def __init__(self, results):
        self.results = results

    def retrieve(self, query: str):
        assert query
        return self.results


def _result(chunk_id: str, score: float):
    return SimpleNamespace(node=SimpleNamespace(node_id=chunk_id), score=score)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        stock_sql_db_path=tmp_path / "retrieval.db",
        stock_storage_base_dir=tmp_path / "storage",
        stock_filings_base_dir=tmp_path / "filings",
        knowledge_storage_dir=tmp_path / "knowledge",
    )


def _seed_company_and_filing(connection, source_path: Path) -> tuple[int, int]:
    company_repository = CompanyRepository(connection)
    company_repository.initialize()
    company = company_repository.upsert_company(
        CompanyRecord(cik="0000000001", name="Test Company", ticker="TEST")
    )
    assert company.company_id is not None
    FilingRepository(connection).upsert_filings(
        company.company_id,
        [
            FilingRecord(
                company_id=company.company_id,
                accession_number="test-accession",
                form_type="10-K",
                filing_date=date(2025, 1, 31),
                report_date=date(2024, 12, 31),
                fiscal_year=2024,
                fiscal_period="FY",
                document_url="https://example.test/filing.htm",
                local_path=source_path,
            )
        ],
    )
    filing = FilingRepository(connection).get_by_accession("test-accession")
    assert filing is not None
    assert filing.filing_id is not None
    return company.company_id, filing.filing_id


def _chunk(
    company_id: int,
    filing_id: int,
    source_path: Path,
    generation_id: str,
) -> FilingChunk:
    text = "Revenue and risk evidence from the filing."
    return FilingChunk(
        chunk_id=f"chunk-{generation_id}",
        generation_id=generation_id,
        company_id=company_id,
        filing_id=filing_id,
        accession_number="test-accession",
        section_name="business",
        section_title="Business",
        section_order=10,
        chunk_order=0,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_sha256=sha256_file(source_path),
        source_path=source_path,
        token_count=8,
        parser_version="parser-v1",
        splitter_version="splitter-v1",
        created_at="2026-06-20T00:00:00+00:00",
    )


def _state(company_id: int, artifact_path: Path, chunk: FilingChunk) -> RetrievalIndexState:
    return RetrievalIndexState(
        company_id=company_id,
        generation_id=chunk.generation_id,
        source_fingerprint="source-fingerprint",
        parser_version="parser-v1",
        splitter_version="splitter-v1",
        embedding_model="test-model",
        chunk_size=512,
        chunk_overlap=64,
        chunk_set_hash=retrieval_service._chunk_set_hash([chunk]),
        filing_count=1,
        chunk_count=1,
        artifact_path=artifact_path,
        updated_at="2026-06-20T00:00:00+00:00",
    )


def _write_complete_artifacts(state: RetrievalIndexState) -> None:
    vector_dir = state.artifact_path / "vector"
    bm25_dir = state.artifact_path / "bm25"
    vector_dir.mkdir(parents=True, exist_ok=True)
    bm25_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generation_id": state.generation_id,
        "source_fingerprint": state.source_fingerprint,
        "chunk_set_hash": state.chunk_set_hash,
        "chunk_count": state.chunk_count,
    }
    (state.artifact_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    for path in (
        vector_dir / "docstore.json",
        vector_dir / "index_store.json",
        vector_dir / "default__vector_store.json",
        bm25_dir / "retriever.json",
        bm25_dir / "params.index.json",
        bm25_dir / "corpus.jsonl",
    ):
        path.write_text("{}", encoding="utf-8")
