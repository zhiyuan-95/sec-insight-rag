import multiprocessing
import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from src.ingestion import (
    ARELLE_INVENTORY_CACHE,
    ARELLE_INVENTORY_WORKER,
    ARELLE_RESULT_FAILED,
    ArelleFilingRequest,
    ArelleFilingResult,
    process_arelle_inventory,
)
from src.processing.arelle_evidence import finalize_arelle_result


ARELLE_FIXTURE_DIR = Path("data/fixtures/arelle")


def test_process_arelle_inventory_runs_sequentially_then_reuses_exact_cache(
    tmp_path: Path,
) -> None:
    filing_dir = tmp_path / "filing"
    shutil.copytree(ARELLE_FIXTURE_DIR, filing_dir)
    entry_point = filing_dir / "minimal-instance.xbrl"
    requests = (
        _request(entry_point, accession_number="0000320193-24-000001"),
        _request(entry_point, accession_number="0000320193-25-000001"),
    )
    cache_dir = tmp_path / "cache"

    first = process_arelle_inventory(
        requests,
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert first.worker_count == 2
    assert first.cache_hit_count == 0
    assert [item.source for item in first.items] == [
        ARELLE_INVENTORY_WORKER,
        ARELLE_INVENTORY_WORKER,
    ]
    assert [item.result.filing.accession_number for item in first.items] == [
        "0000320193-24-000001",
        "0000320193-25-000001",
    ]
    assert all(item.result.session_closed for item in first.items)
    assert all(
        source.local_path and Path(source.local_path).is_file()
        for item in first.items
        for source in item.result.source_documents
    )
    assert all(
        source.content_sha256 and len(source.content_sha256) == 64
        for item in first.items
        for source in item.result.source_documents
    )
    assert not multiprocessing.active_children()

    second = process_arelle_inventory(
        requests,
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert second.worker_count == 0
    assert second.cache_hit_count == 2
    assert [item.source for item in second.items] == [
        ARELLE_INVENTORY_CACHE,
        ARELLE_INVENTORY_CACHE,
    ]
    assert second.results == first.results
    assert [item.result.to_json() for item in second.items] == [
        item.result.to_json() for item in first.items
    ]
    assert not multiprocessing.active_children()


def test_process_arelle_inventory_records_and_reuses_visible_failure(
    tmp_path: Path,
) -> None:
    entry_point = tmp_path / "invalid.xbrl"
    entry_point.write_text("<not-xbrl/>", encoding="utf-8")
    request = _request(
        entry_point,
        accession_number="0000320193-25-000099",
    )
    cache_dir = tmp_path / "cache"

    first = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert first.worker_count == 1
    assert first.items[0].result.status == ARELLE_RESULT_FAILED
    assert first.items[0].result.facts == ()

    second = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert second.worker_count == 0
    assert second.items[0].source == ARELLE_INVENTORY_CACHE
    assert second.items[0].result == first.items[0].result
    assert second.items[0].result.facts == ()


def test_process_arelle_inventory_preserves_acquisition_content_hash(
    tmp_path: Path,
) -> None:
    filing_dir = tmp_path / "filing"
    shutil.copytree(ARELLE_FIXTURE_DIR, filing_dir)
    entry_point = filing_dir / "minimal-instance.xbrl"
    expected_content = entry_point.read_bytes()
    expected_sha256 = sha256(expected_content).hexdigest()
    entry_point.write_text("<changed-after-acquisition/>", encoding="utf-8")
    request = replace(
        _request(
            entry_point,
            accession_number="0000320193-25-000001",
        ),
        content_sha256=expected_sha256,
    )

    result = process_arelle_inventory(
        (request,),
        cache_dir=tmp_path / "cache",
        timeout_seconds=30.0,
    )

    assert result.worker_count == 1
    assert result.results[0].status == ARELLE_RESULT_FAILED
    assert "content hash" in result.results[0].diagnostics[0].message
    assert not Path(result.items[0].cache_path).exists()

    entry_point.write_bytes(expected_content)
    repaired = process_arelle_inventory(
        (request,),
        cache_dir=tmp_path / "cache",
        timeout_seconds=30.0,
    )

    assert repaired.worker_count == 1
    assert repaired.results[0].status != ARELLE_RESULT_FAILED
    assert Path(repaired.items[0].cache_path).is_file()


def test_process_arelle_inventory_invalidates_changed_dependency(
    tmp_path: Path,
) -> None:
    filing_dir = tmp_path / "filing"
    shutil.copytree(ARELLE_FIXTURE_DIR, filing_dir)
    entry_point = filing_dir / "minimal-instance.xbrl"
    request = _request(
        entry_point,
        accession_number="0000320193-25-000001",
    )
    cache_dir = tmp_path / "cache"

    first = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )
    first_linkbase = next(
        source
        for source in first.results[0].source_documents
        if source.local_path and Path(source.local_path).name == "minimal-linkbase.xml"
    )
    linkbase_path = filing_dir / "minimal-linkbase.xml"
    linkbase_path.write_text(
        linkbase_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    second = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert second.worker_count == 1
    assert second.items[0].source == ARELLE_INVENTORY_WORKER
    second_linkbase = next(
        source
        for source in second.results[0].source_documents
        if source.local_path and Path(source.local_path).name == "minimal-linkbase.xml"
    )
    assert second_linkbase.content_sha256 != first_linkbase.content_sha256


def test_process_arelle_inventory_rejects_and_regenerates_corrupt_cache(
    tmp_path: Path,
) -> None:
    filing_dir = tmp_path / "filing"
    shutil.copytree(ARELLE_FIXTURE_DIR, filing_dir)
    request = _request(
        filing_dir / "minimal-instance.xbrl",
        accession_number="0000320193-25-000001",
    )
    cache_dir = tmp_path / "cache"
    first = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )
    cache_path = Path(first.items[0].cache_path)
    cache_path.write_text("{not-valid-json", encoding="utf-8")

    second = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert second.worker_count == 1
    assert second.items[0].source == ARELLE_INVENTORY_WORKER
    assert ArelleFilingResult.from_json(
        cache_path.read_text(encoding="utf-8")
    ) == second.results[0]


def test_process_arelle_inventory_regenerates_incompatible_cached_result(
    tmp_path: Path,
) -> None:
    filing_dir = tmp_path / "filing"
    shutil.copytree(ARELLE_FIXTURE_DIR, filing_dir)
    request = _request(
        filing_dir / "minimal-instance.xbrl",
        accession_number="0000320193-25-000001",
    )
    cache_dir = tmp_path / "cache"
    first = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )
    cache_path = Path(first.items[0].cache_path)
    outdated = finalize_arelle_result(
        replace(
            first.results[0],
            schema_version="outdated",
            payload_sha256="",
        )
    )
    cache_path.write_text(outdated.to_json(), encoding="utf-8")

    second = process_arelle_inventory(
        (request,),
        cache_dir=cache_dir,
        timeout_seconds=30.0,
    )

    assert second.worker_count == 1
    assert second.results[0].schema_version != "outdated"
    assert ArelleFilingResult.from_json(
        cache_path.read_text(encoding="utf-8")
    ) == second.results[0]


def _request(entry_point: Path, *, accession_number: str) -> ArelleFilingRequest:
    return ArelleFilingRequest(
        cik="0000320193",
        accession_number=accession_number,
        form="10-K",
        filing_date="2025-10-31",
        entry_point_path=str(entry_point),
        source_url="https://www.sec.gov/example/minimal-instance.xbrl",
        content_sha256=None,
    )
