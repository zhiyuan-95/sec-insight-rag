import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import ModuleType

from src.retrieval.models import FilingIndexSummary, IndexSyncResult, RetrievedEvidence


def _load_experiment_module() -> ModuleType:
    module_path = Path("experiments/MS6/retrieval_pipeline.py")
    spec = importlib.util.spec_from_file_location("retrieval_pipeline", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_milestone5_report_labels_sync_cold_and_warm_timings(tmp_path: Path) -> None:
    experiment = _load_experiment_module()
    source_path = tmp_path / "filing.htm"
    source_path.write_text("filing", encoding="utf-8")
    sync_result = IndexSyncResult(
        ticker="TEST",
        cik="0000000001",
        company_id=1,
        status="reused",
        generation_id="generation-1",
        artifact_path=tmp_path / "knowledge" / "generation-1",
        filing_count=17,
        chunk_count=2655,
        filing_summaries=(
            FilingIndexSummary(
                accession_number="test-accession",
                form_type="10-K",
                filing_date=date(2025, 1, 31),
                source_path=source_path,
                source_sha256="source-sha",
                section_names=("business",),
                chunk_count=10,
                used_fallback=False,
            ),
        ),
        warnings=(),
        elapsed_seconds=1.25,
    )
    evidence = (
        RetrievedEvidence(
            rank=1,
            chunk_id="chunk-1",
            text="Revenue and risk evidence.",
            ticker="TEST",
            cik="0000000001",
            form_type="10-K",
            filing_date=date(2025, 1, 31),
            accession_number="test-accession",
            section_name="business",
            section_title="Business",
            source_url="https://example.test/filing.htm",
            source_path=source_path,
            text_sha256="text-sha",
            vector_score=0.9,
            vector_rank=1,
            bm25_score=7.5,
            bm25_rank=1,
            fused_score=0.1,
        ),
    )

    report = experiment._render_report(
        mode="local",
        sync_result=sync_result,
        query_runs=(
            experiment.QueryRun(
                query="first query",
                timing_label="initial cold-query duration",
                evidence=evidence,
                elapsed_seconds=3.2,
            ),
            experiment.QueryRun(
                query="second query",
                timing_label="subsequent warm-query duration",
                evidence=evidence,
                elapsed_seconds=0.4,
            ),
        ),
        database_path=tmp_path / "experiment.db",
        knowledge_storage=tmp_path / "knowledge",
        embedding_model="test-model",
        chunk_size=512,
        chunk_overlap=64,
        embedding_model_cached_before_sync=True,
        captured_output="",
    )

    assert "ticker: TEST" in report
    assert "embedding_model: test-model" in report
    assert "embedding_model_cached_before_sync: yes" in report
    assert "chunk_size: 512" in report
    assert "chunk_overlap: 64" in report
    assert "active_filing_count: 17" in report
    assert "chunk_count: 2655" in report
    assert "retrieval_synchronization_duration_seconds: 1.250" in report
    assert "initial cold-query duration: 3.200 seconds" in report
    assert "subsequent warm-query duration: 0.400 seconds" in report
