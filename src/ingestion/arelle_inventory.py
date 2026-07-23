"""Sequential processing and verified caching for annual Arelle inventory."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib.metadata import version
from pathlib import Path

from src.ingestion.arelle_worker import process_arelle_accession
from src.ingestion.tickers import normalize_cik
from src.processing.arelle_evidence import (
    ARELLE_ADAPTER_VERSION,
    ARELLE_RESULT_COMPLETE,
    ARELLE_RESULT_FAILED,
    ARELLE_RESULT_SCHEMA_VERSION,
    ArelleFilingRequest,
    ArelleFilingResult,
    ArelleSourceDocumentRecord,
)
from src.processing.arelle_extraction import file_sha256

ARELLE_INVENTORY_CACHE = "cache"
ARELLE_INVENTORY_WORKER = "worker"
ARELLE_INPUT_MANIFEST_VERSION = "1"


@dataclass(frozen=True)
class ArelleInventoryItem:
    """One accession result and how the inventory obtained it."""

    result: ArelleFilingResult
    source: str
    cache_path: str


@dataclass(frozen=True)
class ArelleInventoryResult:
    """Ordered results for one selected annual filing inventory."""

    items: tuple[ArelleInventoryItem, ...]

    @property
    def results(self) -> tuple[ArelleFilingResult, ...]:
        return tuple(item.result for item in self.items)

    @property
    def worker_count(self) -> int:
        return sum(item.source == ARELLE_INVENTORY_WORKER for item in self.items)

    @property
    def cache_hit_count(self) -> int:
        return sum(item.source == ARELLE_INVENTORY_CACHE for item in self.items)


def process_arelle_inventory(
    requests: Sequence[ArelleFilingRequest],
    *,
    cache_dir: Path,
    timeout_seconds: float | None = None,
) -> ArelleInventoryResult:
    """Process locally acquired annual accessions sequentially with exact caching."""
    items: list[ArelleInventoryItem] = []
    for request in requests:
        prepared_request = _prepare_request(request)
        cache_path = _result_cache_path(cache_dir, prepared_request)
        cached_result = _read_valid_cached_result(
            cache_path,
            prepared_request,
            cache_dir,
        )
        if cached_result is not None:
            items.append(
                ArelleInventoryItem(
                    result=cached_result,
                    source=ARELLE_INVENTORY_CACHE,
                    cache_path=str(cache_path),
                )
            )
            continue

        result = process_arelle_accession(
            prepared_request,
            timeout_seconds=timeout_seconds,
        )
        if _entry_point_matches_request(prepared_request) and result.status in {
            ARELLE_RESULT_COMPLETE,
            ARELLE_RESULT_FAILED,
        }:
            _write_cached_result(
                cache_path,
                result,
                prepared_request,
                cache_dir,
            )
        items.append(
            ArelleInventoryItem(
                result=result,
                source=ARELLE_INVENTORY_WORKER,
                cache_path=str(cache_path),
            )
        )
    return ArelleInventoryResult(items=tuple(items))


def _prepare_request(request: ArelleFilingRequest) -> ArelleFilingRequest:
    entry_point = Path(request.entry_point_path).resolve()
    observed_sha256 = file_sha256(entry_point) if entry_point.is_file() else None
    content_sha256 = request.content_sha256 or observed_sha256
    return replace(
        request,
        cik=normalize_cik(request.cik),
        entry_point_path=str(entry_point),
        content_sha256=content_sha256,
    )


def _result_cache_path(cache_dir: Path, request: ArelleFilingRequest) -> Path:
    accession_number = request.accession_number.strip()
    if not accession_number or any(
        part in accession_number for part in ("/", "\\", "..")
    ):
        raise ValueError("Arelle accession number is unsafe for cache storage")
    base = cache_dir.resolve()
    path = (base / request.cik / accession_number / "result.json").resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("Arelle cache path escaped the configured directory") from exc
    return path


def _read_valid_cached_result(
    cache_path: Path,
    request: ArelleFilingRequest,
    cache_dir: Path,
) -> ArelleFilingResult | None:
    if not cache_path.is_file() or not _entry_point_matches_request(request):
        return None
    if not _input_manifest_matches(cache_path, request, cache_dir):
        return None
    try:
        result = ArelleFilingResult.from_json(
            cache_path.read_text(encoding="utf-8")
        )
    except (OSError, TypeError, UnicodeDecodeError, ValueError):
        return None
    if result.status not in {ARELLE_RESULT_COMPLETE, ARELLE_RESULT_FAILED}:
        return None
    if (
        result.schema_version != ARELLE_RESULT_SCHEMA_VERSION
        or result.adapter_version != ARELLE_ADAPTER_VERSION
        or result.arelle_version != version("arelle-release")
        or result.content_sha256 != request.content_sha256
    ):
        return None
    if not _filing_identity_matches(result, request):
        return None
    if result.status == ARELLE_RESULT_FAILED:
        return result if _failed_result_is_empty(result) else None
    if not result.source_documents or not all(
        _source_document_matches(document) for document in result.source_documents
    ):
        return None
    return result


def _filing_identity_matches(
    result: ArelleFilingResult,
    request: ArelleFilingRequest,
) -> bool:
    filing = result.filing
    return (
        filing.cik == request.cik
        and filing.accession_number == request.accession_number
        and filing.form == request.form
        and filing.filing_date == request.filing_date
        and filing.entry_point_path == request.entry_point_path
        and filing.source_url == request.source_url
    )


def _entry_point_matches_request(request: ArelleFilingRequest) -> bool:
    if request.content_sha256 is None:
        return False
    path = Path(request.entry_point_path)
    return path.is_file() and file_sha256(path) == request.content_sha256


def _source_document_matches(document: ArelleSourceDocumentRecord) -> bool:
    if document.content_sha256 is None or document.local_path is None:
        return False
    path = Path(document.local_path)
    return path.is_file() and file_sha256(path) == document.content_sha256


def _failed_result_is_empty(result: ArelleFilingResult) -> bool:
    return not any(
        (
            result.facts,
            result.concepts,
            result.contexts,
            result.units,
            result.relationships,
            result.formula_assertions,
            result.namespaces,
            result.source_documents,
        )
    )


def _input_manifest_matches(
    cache_path: Path,
    request: ArelleFilingRequest,
    cache_dir: Path,
) -> bool:
    manifest_path = cache_path.with_name("inputs.json")
    try:
        cached_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current_manifest = _build_input_manifest(request, cache_dir)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return cached_manifest == current_manifest


def _build_input_manifest(
    request: ArelleFilingRequest,
    cache_dir: Path,
) -> dict[str, object]:
    entry_point = Path(request.entry_point_path)
    input_root = entry_point.parent.resolve()
    cache_root = cache_dir.resolve()
    if _is_within(input_root, cache_root):
        raise ValueError(
            "Arelle cache directory cannot contain the acquired filing directory"
        )
    files: list[dict[str, str]] = []
    for path in sorted(input_root.rglob("*"), key=lambda item: str(item)):
        if not path.is_file() or _is_within(path.resolve(), cache_root):
            continue
        files.append(
            {
                "path": path.relative_to(input_root).as_posix(),
                "sha256": file_sha256(path),
            }
        )
    return {
        "manifest_version": ARELLE_INPUT_MANIFEST_VERSION,
        "entry_point": entry_point.relative_to(input_root).as_posix(),
        "files": files,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_cached_result(
    cache_path: Path,
    result: ArelleFilingResult,
    request: ArelleFilingRequest,
    cache_dir: Path,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_path.with_name("inputs.json")
    temporary_manifest_path = manifest_path.with_suffix(".json.tmp")
    temporary_manifest_path.write_text(
        json.dumps(
            _build_input_manifest(request, cache_dir),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary_path = cache_path.with_suffix(".json.tmp")
    temporary_path.write_text(result.to_json(), encoding="utf-8")
    # Publish the manifest last so an interrupted refresh cannot pair an old
    # failed result with a new input snapshot and make that failure reusable.
    temporary_path.replace(cache_path)
    temporary_manifest_path.replace(manifest_path)
