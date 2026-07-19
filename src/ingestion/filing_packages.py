"""Build and verify accession-scoped local XBRL filing packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.ingestion.errors import FilingPackageError
from src.ingestion.filings import FilingMetadata
from src.ingestion.sec_client import SecClient
from src.processing.arelle_records import ArelleResourceLimits


FILING_PACKAGE_SCHEMA_VERSION = 1
FILING_PACKAGE_POLICY_VERSION = "filing-package-policy-v1"
_COPY_CHUNK_BYTES = 1024 * 1024
_XBRL_FILE_SUFFIXES = (".xsd", ".xml")

OfflinePackageVerifier = Callable[[Path, tuple[Path, ...]], None]


@dataclass(frozen=True)
class FilingPackageFile:
    """One immutable filing-owned artifact in a package manifest."""

    relative_path: str
    source_url: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class FilingPackageTaxonomy:
    """One installed taxonomy archive used by offline verification."""

    archive_filename: str
    install_mode: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class FilingPackageManifest:
    """Verified accession package identity and content inventory."""

    manifest_schema_version: int
    package_policy_version: str
    cik: str
    accession_number: str
    form: str
    filing_date: str
    entry_document: str
    source_directory_url: str
    taxonomy_registry_sha256: str
    taxonomy_packages: tuple[FilingPackageTaxonomy, ...]
    files: tuple[FilingPackageFile, ...]
    verification_status: str


def build_filing_package(
    client: SecClient,
    filing: FilingMetadata,
    base_directory: str | Path,
    *,
    taxonomy_registry_hash: str,
    taxonomy_package_paths: Sequence[str | Path] = (),
    offline_verifier: OfflinePackageVerifier | None = None,
    limits: ArelleResourceLimits = ArelleResourceLimits(),
) -> Path:
    """Download filing-owned XBRL artifacts and publish one atomic package."""
    taxonomy_registry_hash = _sha256_text(
        taxonomy_registry_hash,
        "taxonomy_registry_hash",
    )
    base = Path(base_directory).resolve()
    package_root = _package_root(base, filing, taxonomy_registry_hash)
    manifest_path = package_root / "manifest.json"
    if package_root.exists():
        existing = verify_filing_package(
            manifest_path,
            limits=limits,
            expected_accession_number=filing.accession_number,
            require_arelle_verification=offline_verifier is not None,
        )
        requested_taxonomies = tuple(
            _taxonomy_record(Path(path).resolve()) for path in taxonomy_package_paths
        )
        if existing.taxonomy_registry_sha256 != taxonomy_registry_hash:
            raise FilingPackageError(
                "Existing filing package uses a different taxonomy registry; "
                "remove the generated package and rebuild it"
            )
        if existing.taxonomy_packages != requested_taxonomies:
            raise FilingPackageError(
                "Existing filing package uses different taxonomy artifacts; "
                "remove the generated package and rebuild it"
            )
        return manifest_path

    source_directory_url = filing.document_url.rsplit("/", 1)[0]
    _require_sec_archive_url(source_directory_url, filing)
    index_payload = client.get_json(f"{source_directory_url}/index.json")
    artifacts = _select_filing_artifacts(index_payload, filing.primary_document)
    if len(artifacts) > limits.max_package_files:
        raise FilingPackageError(
            f"Filing package contains too many files: {len(artifacts)}"
        )
    declared_total = sum(size for _, size in artifacts)
    if declared_total > limits.max_package_bytes:
        raise FilingPackageError(
            f"Filing package exceeds {limits.max_package_bytes} declared bytes"
        )

    package_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".xbrl-package-", dir=package_root.parent)
    ).resolve()
    try:
        filing_dir = staging / "filing"
        filing_dir.mkdir()
        files: list[FilingPackageFile] = []
        actual_total = 0
        for filename, declared_size in artifacts:
            source_url = f"{source_directory_url}/{filename}"
            _require_sec_archive_url(source_url, filing)
            body = client.get_bytes(source_url, accept="*/*")
            if len(body) != declared_size:
                raise FilingPackageError(
                    f"SEC index size mismatch for {filename}: "
                    f"expected {declared_size}, got {len(body)}"
                )
            actual_total += len(body)
            if actual_total > limits.max_package_bytes:
                raise FilingPackageError(
                    f"Filing package exceeds {limits.max_package_bytes} bytes"
                )
            target = _safe_relative_file(filing_dir, filename)
            target.write_bytes(body)
            files.append(
                FilingPackageFile(
                    relative_path=f"filing/{filename}",
                    source_url=source_url,
                    byte_size=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                )
            )

        entry_document = f"filing/{_safe_filename(filing.primary_document)}"
        taxonomy_paths = tuple(Path(path).resolve() for path in taxonomy_package_paths)
        taxonomy_records = tuple(_taxonomy_record(path) for path in taxonomy_paths)
        status = "files_verified"
        if offline_verifier is not None:
            offline_verifier(staging / entry_document, taxonomy_paths)
            status = "arelle_offline_verified"
        manifest = FilingPackageManifest(
            manifest_schema_version=FILING_PACKAGE_SCHEMA_VERSION,
            package_policy_version=FILING_PACKAGE_POLICY_VERSION,
            cik=filing.cik,
            accession_number=filing.accession_number,
            form=filing.form,
            filing_date=filing.filing_date,
            entry_document=entry_document,
            source_directory_url=source_directory_url,
            taxonomy_registry_sha256=taxonomy_registry_hash,
            taxonomy_packages=taxonomy_records,
            files=tuple(sorted(files, key=lambda item: item.relative_path)),
            verification_status=status,
        )
        (staging / "manifest.json").write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_filing_package(
            staging / "manifest.json",
            limits=limits,
            expected_accession_number=filing.accession_number,
            require_arelle_verification=offline_verifier is not None,
        )
        os.replace(staging, package_root)
    except FilingPackageError:
        _remove_staging_directory(staging, package_root.parent)
        raise
    except Exception as exc:
        _remove_staging_directory(staging, package_root.parent)
        raise FilingPackageError(
            f"Could not build filing package for {filing.accession_number}: {exc}"
        ) from exc
    return manifest_path


def load_filing_package_manifest(path: str | Path) -> FilingPackageManifest:
    """Load a manifest without trusting any referenced files."""
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FilingPackageError(
            f"Filing package manifest does not exist: {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FilingPackageError("Filing package manifest is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FilingPackageError("Filing package manifest must be an object")
    try:
        files = tuple(
            FilingPackageFile(
                relative_path=str(item["relative_path"]),
                source_url=str(item["source_url"]),
                byte_size=_positive_int(item["byte_size"], "file byte_size"),
                sha256=_sha256_text(item["sha256"], "file sha256"),
            )
            for item in value["files"]
        )
        taxonomy_packages = tuple(
            FilingPackageTaxonomy(
                archive_filename=_safe_filename(str(item["archive_filename"])),
                install_mode=_taxonomy_install_mode(item["install_mode"]),
                byte_size=_positive_int(item["byte_size"], "taxonomy byte_size"),
                sha256=_sha256_text(item["sha256"], "taxonomy sha256"),
            )
            for item in value.get("taxonomy_packages", [])
        )
        manifest = FilingPackageManifest(
            manifest_schema_version=int(value["manifest_schema_version"]),
            package_policy_version=_nonblank(value["package_policy_version"], "package_policy_version"),
            cik=_nonblank(value["cik"], "cik"),
            accession_number=_nonblank(value["accession_number"], "accession_number"),
            form=_nonblank(value["form"], "form"),
            filing_date=_nonblank(value["filing_date"], "filing_date"),
            entry_document=str(value["entry_document"]),
            source_directory_url=_nonblank(value["source_directory_url"], "source_directory_url"),
            taxonomy_registry_sha256=_sha256_text(
                value["taxonomy_registry_sha256"], "taxonomy_registry_sha256"
            ),
            taxonomy_packages=taxonomy_packages,
            files=files,
            verification_status=_nonblank(value["verification_status"], "verification_status"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FilingPackageError("Filing package manifest shape is invalid") from exc
    if manifest.manifest_schema_version != FILING_PACKAGE_SCHEMA_VERSION:
        raise FilingPackageError("Unsupported filing package manifest schema version")
    if manifest.package_policy_version != FILING_PACKAGE_POLICY_VERSION:
        raise FilingPackageError("Unsupported filing package policy version")
    return manifest


def verify_filing_package(
    manifest_path: str | Path,
    *,
    limits: ArelleResourceLimits = ArelleResourceLimits(),
    expected_accession_number: str | None = None,
    require_arelle_verification: bool = True,
) -> FilingPackageManifest:
    """Verify package paths, sizes, hashes, identity, and proof status."""
    path = Path(manifest_path).resolve()
    package_root = path.parent
    manifest = load_filing_package_manifest(path)
    if (
        expected_accession_number is not None
        and manifest.accession_number != expected_accession_number
    ):
        raise FilingPackageError("Filing package accession does not match request")
    if require_arelle_verification and manifest.verification_status != "arelle_offline_verified":
        raise FilingPackageError("Filing package has not passed offline Arelle verification")
    if manifest.verification_status not in {"files_verified", "arelle_offline_verified"}:
        raise FilingPackageError("Filing package verification status is invalid")
    if not manifest.files:
        raise FilingPackageError("Filing package contains no filing artifacts")
    if len(manifest.files) > limits.max_package_files:
        raise FilingPackageError("Filing package file count exceeds resource policy")
    identities = [item.relative_path.casefold() for item in manifest.files]
    if len(identities) != len(set(identities)):
        raise FilingPackageError("Filing package contains duplicate normalized paths")

    total_bytes = 0
    for item in manifest.files:
        artifact = _safe_manifest_path(package_root, item.relative_path)
        if not artifact.is_file():
            raise FilingPackageError(
                f"Filing package artifact does not exist: {item.relative_path}"
            )
        size = artifact.stat().st_size
        if size != item.byte_size:
            raise FilingPackageError(
                f"Filing package size mismatch: {item.relative_path}"
            )
        if _sha256_file(artifact) != item.sha256:
            raise FilingPackageError(
                f"Filing package hash mismatch: {item.relative_path}"
            )
        total_bytes += size
        if total_bytes > limits.max_package_bytes:
            raise FilingPackageError("Filing package exceeds resource policy byte limit")
    entry_path = _safe_manifest_path(package_root, manifest.entry_document)
    if manifest.entry_document.casefold() not in set(identities):
        raise FilingPackageError("Filing package entry document is not in its inventory")
    if not entry_path.is_file():
        raise FilingPackageError("Filing package entry document does not exist")
    return manifest


def filing_package_sha256(manifest_path: str | Path) -> str:
    """Hash the exact verified manifest for future result-cache identity."""
    path = Path(manifest_path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise FilingPackageError(f"Filing package manifest does not exist: {path}") from exc


def _select_filing_artifacts(
    index_payload: dict[str, Any],
    primary_document: str,
) -> tuple[tuple[str, int], ...]:
    directory = index_payload.get("directory")
    if not isinstance(directory, dict):
        raise FilingPackageError("SEC filing index is missing its directory object")
    raw_items = directory.get("item")
    if not isinstance(raw_items, list):
        raise FilingPackageError("SEC filing index is missing its item list")
    primary = _safe_filename(primary_document)
    selected: dict[str, int] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise FilingPackageError("SEC filing index item is not an object")
        filename = _safe_filename(_nonblank(item.get("name"), "index filename"))
        lowered = filename.lower()
        if filename != primary and not lowered.endswith(_XBRL_FILE_SUFFIXES):
            continue
        size = _positive_int(item.get("size"), f"index size for {filename}")
        normalized = filename.casefold()
        if normalized in {name.casefold() for name in selected}:
            raise FilingPackageError("SEC filing index contains duplicate normalized paths")
        selected[filename] = size
    if primary not in selected:
        raise FilingPackageError("SEC filing index does not contain the primary document")
    return tuple(sorted(selected.items()))


def _package_root(
    base: Path,
    filing: FilingMetadata,
    taxonomy_registry_hash: str,
) -> Path:
    target = (
        base
        / _safe_filename(filing.cik)
        / _safe_filename(filing.accession_number)
        / f"xbrl-package-{taxonomy_registry_hash[:12]}"
    ).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise FilingPackageError("Filing package path escaped configured storage") from exc
    return target


def _safe_relative_file(root: Path, filename: str) -> Path:
    target = (root / _safe_filename(filename)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise FilingPackageError("Filing artifact path escaped staging directory") from exc
    return target


def _safe_manifest_path(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise FilingPackageError("Filing package manifest contains an unsafe path")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise FilingPackageError("Filing package manifest path escaped package root") from exc
    return target


def _safe_filename(value: str) -> str:
    filename = value.strip()
    if (
        not filename
        or Path(filename).name != filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or ".." in filename
    ):
        raise FilingPackageError(f"Unsafe filing package filename: {value}")
    return filename


def _require_sec_archive_url(url: str, filing: FilingMetadata) -> None:
    parsed = urlparse(url)
    expected_path = (
        f"/Archives/edgar/data/{int(filing.cik)}/"
        f"{filing.accession_number.replace('-', '')}"
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.sec.gov"
        or not parsed.path.startswith(expected_path)
    ):
        raise FilingPackageError(f"Unapproved filing package source URL: {url}")


def _taxonomy_record(path: Path) -> FilingPackageTaxonomy:
    if not path.is_file():
        raise FilingPackageError(f"Taxonomy package does not exist: {path}")
    return FilingPackageTaxonomy(
        archive_filename=_safe_filename(path.name),
        install_mode=_taxonomy_archive_install_mode(path),
        byte_size=path.stat().st_size,
        sha256=_sha256_file(path),
    )


def _taxonomy_archive_install_mode(path: Path) -> str:
    from src.ingestion.taxonomy_packages import taxonomy_archive_install_mode

    return taxonomy_archive_install_mode(path)


def _taxonomy_install_mode(value: Any) -> str:
    mode = _nonblank(value, "taxonomy install_mode")
    if mode not in {
        "arelle_package",
        "web_cache_archive",
        "web_cache_overlay",
    }:
        raise FilingPackageError(f"Unsupported taxonomy install mode: {mode}")
    return mode


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: Any, field_name: str) -> str:
    text = _nonblank(value, field_name).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise FilingPackageError(f"{field_name} must be a SHA-256 hex digest")
    return text


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise FilingPackageError(f"{field_name} must be a positive integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise FilingPackageError(f"{field_name} must be a positive integer") from exc
    if integer <= 0:
        raise FilingPackageError(f"{field_name} must be a positive integer")
    return integer


def _nonblank(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FilingPackageError(f"{field_name} cannot be blank")
    return value.strip()


def _remove_staging_directory(staging: Path, expected_parent: Path) -> None:
    resolved = staging.resolve()
    if resolved.parent != expected_parent.resolve() or not resolved.name.startswith(
        ".xbrl-package-"
    ):
        raise FilingPackageError("Refused to clean an unexpected staging directory")
    shutil.rmtree(resolved, ignore_errors=True)
