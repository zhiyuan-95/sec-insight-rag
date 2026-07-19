"""Validate and install source-approved Arelle taxonomy packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from src.ingestion.errors import TaxonomyPackageError


DEFAULT_REGISTRY_PATH = Path("data/taxonomy_packages.json")
DEFAULT_INSTALL_DIRECTORY = Path("data_store/taxonomy_packages")
REGISTRY_SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class TaxonomyPackageEntry:
    """One source-approved immutable package artifact."""

    package_id: str
    version: str
    source_url: str
    approved_redirect_hosts: tuple[str, ...]
    archive_filename: str
    install_mode: str
    byte_size: int
    sha256: str
    namespaces: tuple[str, ...]
    catalog_remappings: tuple[tuple[str, str], ...]
    compatible_arelle: str
    approval_date: str

    @property
    def approved_hosts(self) -> frozenset[str]:
        source_host = _url_host(self.source_url)
        return frozenset({source_host, *self.approved_redirect_hosts})


@dataclass(frozen=True)
class TaxonomyPackageRegistry:
    """Validated source-controlled registry document."""

    registry_schema_version: int
    registry_policy_version: str
    packages: tuple[TaxonomyPackageEntry, ...]


@dataclass(frozen=True)
class SyncedTaxonomyPackage:
    """One verified local install outcome."""

    package_id: str
    version: str
    path: Path
    status: str
    sha256: str
    byte_size: int


PackageDownloader = Callable[[TaxonomyPackageEntry, Path], None]


def load_taxonomy_package_registry(
    path: str | Path = DEFAULT_REGISTRY_PATH,
) -> TaxonomyPackageRegistry:
    """Load and strictly validate the source-controlled registry."""
    registry_path = Path(path)
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaxonomyPackageError(
            f"Taxonomy package registry does not exist: {registry_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise TaxonomyPackageError(
            f"Taxonomy package registry is not valid JSON: {registry_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise TaxonomyPackageError("Taxonomy package registry must be an object")
    if payload.get("registry_schema_version") != REGISTRY_SCHEMA_VERSION:
        raise TaxonomyPackageError(
            "Unsupported taxonomy package registry schema version"
        )
    policy_version = _required_text(payload, "registry_policy_version")
    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list):
        raise TaxonomyPackageError("Taxonomy package registry packages must be a list")

    packages = tuple(_entry_from_dict(item) for item in raw_packages)
    identities = [(entry.package_id, entry.version) for entry in packages]
    if len(identities) != len(set(identities)):
        raise TaxonomyPackageError("Taxonomy package registry contains duplicate identities")
    filenames = [entry.archive_filename.casefold() for entry in packages]
    if len(filenames) != len(set(filenames)):
        raise TaxonomyPackageError("Taxonomy package registry contains duplicate filenames")
    return TaxonomyPackageRegistry(
        registry_schema_version=REGISTRY_SCHEMA_VERSION,
        registry_policy_version=policy_version,
        packages=packages,
    )


def taxonomy_registry_sha256(path: str | Path = DEFAULT_REGISTRY_PATH) -> str:
    """Hash the exact reviewed registry bytes for cache fingerprints."""
    registry_path = Path(path)
    try:
        return hashlib.sha256(registry_path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise TaxonomyPackageError(
            f"Taxonomy package registry does not exist: {registry_path}"
        ) from exc


def sync_taxonomy_packages(
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    install_directory: str | Path = DEFAULT_INSTALL_DIRECTORY,
    *,
    downloader: PackageDownloader | None = None,
) -> tuple[SyncedTaxonomyPackage, ...]:
    """Install missing packages and verify every existing artifact."""
    registry = load_taxonomy_package_registry(registry_path)
    install_root = Path(install_directory).resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    download = downloader or _download_package
    outcomes: list[SyncedTaxonomyPackage] = []
    for entry in registry.packages:
        target = _safe_install_path(install_root, entry.archive_filename)
        if target.exists():
            _verify_package_file(target, entry)
            outcomes.append(_sync_outcome(entry, target, "reused"))
            continue

        temp_path = _new_temp_path(install_root, entry.archive_filename)
        try:
            download(entry, temp_path)
            _verify_package_file(temp_path, entry)
            os.replace(temp_path, target)
        except TaxonomyPackageError:
            _remove_if_present(temp_path)
            raise
        except Exception as exc:
            _remove_if_present(temp_path)
            raise TaxonomyPackageError(
                f"Could not install taxonomy package {entry.package_id} {entry.version}: {exc}"
            ) from exc
        outcomes.append(_sync_outcome(entry, target, "installed"))
    return tuple(outcomes)


def installed_taxonomy_package_paths(
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    install_directory: str | Path = DEFAULT_INSTALL_DIRECTORY,
) -> tuple[Path, ...]:
    """Return verified paths without downloading anything."""
    registry = load_taxonomy_package_registry(registry_path)
    root = Path(install_directory).resolve()
    paths: list[Path] = []
    for entry in registry.packages:
        path = _safe_install_path(root, entry.archive_filename)
        if not path.exists():
            raise TaxonomyPackageError(
                f"Approved taxonomy package is not installed: {entry.package_id} {entry.version}"
            )
        _verify_package_file(path, entry)
        paths.append(path)
    return tuple(paths)


def _entry_from_dict(value: Any) -> TaxonomyPackageEntry:
    if not isinstance(value, dict):
        raise TaxonomyPackageError("Taxonomy package entry must be an object")
    package_id = _required_text(value, "package_id")
    version = _required_text(value, "version")
    source_url = _required_text(value, "source_url")
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise TaxonomyPackageError(
            f"Taxonomy package {package_id} source_url must use HTTPS"
        )
    archive_filename = _safe_filename(_required_text(value, "archive_filename"))
    byte_size = value.get("byte_size")
    if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
        raise TaxonomyPackageError(
            f"Taxonomy package {package_id} byte_size must be a positive integer"
        )
    sha256 = _required_text(value, "sha256").lower()
    if not _SHA256_PATTERN.fullmatch(sha256):
        raise TaxonomyPackageError(
            f"Taxonomy package {package_id} sha256 must be 64 lowercase hex characters"
        )
    redirect_hosts = _text_tuple(value.get("approved_redirect_hosts", []), "approved_redirect_hosts")
    normalized_redirect_hosts = tuple(_normalize_host(host) for host in redirect_hosts)
    namespaces = _text_tuple(value.get("namespaces", []), "namespaces")
    raw_remappings = value.get("catalog_remappings", {})
    if not isinstance(raw_remappings, dict):
        raise TaxonomyPackageError(
            f"Taxonomy package {package_id} catalog_remappings must be an object"
        )
    remappings = tuple(
        sorted(
            (
                _nonblank_text(prefix, "catalog remapping prefix"),
                _nonblank_text(rewrite, "catalog remapping target"),
            )
            for prefix, rewrite in raw_remappings.items()
        )
    )
    return TaxonomyPackageEntry(
        package_id=package_id,
        version=version,
        source_url=source_url,
        approved_redirect_hosts=normalized_redirect_hosts,
        archive_filename=archive_filename,
        install_mode=_install_mode(value.get("install_mode", "arelle_package")),
        byte_size=byte_size,
        sha256=sha256,
        namespaces=namespaces,
        catalog_remappings=remappings,
        compatible_arelle=_required_text(value, "compatible_arelle"),
        approval_date=_required_text(value, "approval_date"),
    )


def _download_package(entry: TaxonomyPackageEntry, target: Path) -> None:
    request = Request(
        entry.source_url,
        headers={"User-Agent": "sec-insight-rag taxonomy package sync"},
    )
    opener = build_opener(_ApprovedRedirectHandler(entry.approved_hosts))
    written = 0
    try:
        with opener.open(request, timeout=60) as response, target.open("wb") as output:
            final_host = _url_host(response.geturl())
            if final_host not in entry.approved_hosts:
                raise TaxonomyPackageError(
                    f"Taxonomy package redirected to unapproved host: {final_host}"
                )
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > entry.byte_size:
                    raise TaxonomyPackageError(
                        f"Taxonomy package exceeded expected size: {entry.package_id}"
                    )
                output.write(chunk)
    except TaxonomyPackageError:
        raise
    except Exception as exc:
        raise TaxonomyPackageError(
            f"Taxonomy package download failed for {entry.package_id}: {exc}"
        ) from exc


class _ApprovedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, approved_hosts: frozenset[str]) -> None:
        super().__init__()
        self._approved_hosts = approved_hosts

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        host = _url_host(newurl)
        if host not in self._approved_hosts:
            raise TaxonomyPackageError(
                f"Taxonomy package redirect host is not approved: {host}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _verify_package_file(path: Path, entry: TaxonomyPackageEntry) -> None:
    size = path.stat().st_size
    if size != entry.byte_size:
        raise TaxonomyPackageError(
            f"Taxonomy package size mismatch for {entry.package_id}: "
            f"expected {entry.byte_size}, got {size}"
        )
    digest = _sha256_file(path)
    if digest != entry.sha256:
        raise TaxonomyPackageError(
            f"Taxonomy package hash mismatch for {entry.package_id}"
        )
    actual_mode = taxonomy_archive_install_mode(
        path,
        archive_filename=entry.archive_filename,
    )
    if actual_mode != entry.install_mode:
        raise TaxonomyPackageError(
            f"Taxonomy package install mode mismatch for {entry.package_id}: "
            f"expected {entry.install_mode}, got {actual_mode}"
        )


def taxonomy_archive_install_mode(
    path: str | Path,
    *,
    archive_filename: str | None = None,
) -> str:
    """Classify a verified ZIP as an Arelle package or approved web-cache archive."""
    archive = Path(path)
    try:
        with zipfile.ZipFile(archive) as zipped:
            files = [item for item in zipped.infolist() if not item.is_dir()]
            if len(files) > 100_000:
                raise TaxonomyPackageError(
                    f"Taxonomy archive contains too many files: {archive.name}"
                )
            total_size = 0
            normalized_names: set[str] = set()
            for item in files:
                normalized = _safe_archive_member(item.filename)
                folded = normalized.casefold()
                if folded in normalized_names:
                    raise TaxonomyPackageError(
                        f"Taxonomy archive contains duplicate paths: {archive.name}"
                    )
                normalized_names.add(folded)
                total_size += item.file_size
                if total_size > 1 * 1024 * 1024 * 1024:
                    raise TaxonomyPackageError(
                        f"Taxonomy archive expands beyond 1 GiB: {archive.name}"
                    )
            if any(
                name.endswith("/meta-inf/taxonomypackage.xml")
                or name == "meta-inf/taxonomypackage.xml"
                for name in normalized_names
            ):
                return "arelle_package"
            if files and all(_is_sec_cache_member(item.filename) for item in files):
                return "web_cache_archive"
            if files and _is_sec_overlay_archive(
                archive_filename or archive.name,
                files,
            ):
                return "web_cache_overlay"
    except zipfile.BadZipFile as exc:
        raise TaxonomyPackageError(
            f"Taxonomy package is not a valid ZIP archive: {archive.name}"
        ) from exc
    raise TaxonomyPackageError(
        f"Taxonomy archive format is not approved: {archive.name}"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_mode(value: Any) -> str:
    mode = _nonblank_text(value, "install_mode")
    if mode not in {
        "arelle_package",
        "web_cache_archive",
        "web_cache_overlay",
    }:
        raise TaxonomyPackageError(f"Unsupported taxonomy install_mode: {mode}")
    return mode


def _safe_archive_member(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if (
        not normalized
        or value.startswith(("/", "\\"))
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
    ):
        raise TaxonomyPackageError(f"Unsafe taxonomy archive path: {value}")
    return normalized


def _is_sec_cache_member(value: str) -> bool:
    normalized = _safe_archive_member(value)
    parts = normalized.split("/")
    if len(parts) >= 3 and parts[0].lower() == "xbrl.sec.gov":
        return True
    return (
        len(parts) >= 3
        and len(parts[0]) in {4, 6}
        and parts[0][:4].isdigit()
        and parts[1].lower() == "xbrl.sec.gov"
    )


def _is_sec_overlay_archive(
    archive_filename: str,
    files: list[zipfile.ZipInfo],
) -> bool:
    stem = archive_filename.removesuffix(".zip")
    if "-" not in stem:
        return False
    taxonomy_name, version = stem.rsplit("-", 1)
    if (
        not taxonomy_name
        or not version[:4].isdigit()
        or any("/" in _safe_archive_member(item.filename) for item in files)
    ):
        return False
    return all(
        _safe_archive_member(item.filename).lower().startswith(
            taxonomy_name.lower() + "-"
        )
        for item in files
    )


def _sync_outcome(
    entry: TaxonomyPackageEntry,
    path: Path,
    status: str,
) -> SyncedTaxonomyPackage:
    return SyncedTaxonomyPackage(
        package_id=entry.package_id,
        version=entry.version,
        path=path,
        status=status,
        sha256=entry.sha256,
        byte_size=entry.byte_size,
    )


def _safe_install_path(root: Path, filename: str) -> Path:
    target = (root / _safe_filename(filename)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:  # pragma: no cover - _safe_filename rejects this first
        raise TaxonomyPackageError("Taxonomy package path escaped install directory") from exc
    return target


def _safe_filename(value: str) -> str:
    filename = value.strip()
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise TaxonomyPackageError("Taxonomy archive filename is not safe")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise TaxonomyPackageError("Taxonomy archive filename is not safe")
    return filename


def _new_temp_path(root: Path, filename: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{filename}.",
        suffix=".part",
        dir=root,
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    return path


def _remove_if_present(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _url_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise TaxonomyPackageError("Taxonomy package URL must use HTTPS")
    return _normalize_host(parsed.hostname)


def _normalize_host(host: str) -> str:
    value = host.strip().lower().rstrip(".")
    if not value or "/" in value or ":" in value:
        raise TaxonomyPackageError(f"Invalid approved redirect host: {host}")
    return value


def _required_text(value: dict[str, Any], key: str) -> str:
    if key not in value:
        raise TaxonomyPackageError(f"Taxonomy package registry missing {key}")
    return _nonblank_text(value[key], key)


def _nonblank_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaxonomyPackageError(f"Taxonomy package {field_name} cannot be blank")
    return value.strip()


def _text_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TaxonomyPackageError(f"Taxonomy package {field_name} must be a list")
    return tuple(_nonblank_text(item, field_name) for item in value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync", help="Install approved packages")
    sync_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    sync_parser.add_argument(
        "--install-directory",
        type=Path,
        default=DEFAULT_INSTALL_DIRECTORY,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit taxonomy package utility."""
    args = _build_parser().parse_args(argv)
    if args.command != "sync":  # pragma: no cover - argparse enforces this
        raise TaxonomyPackageError(f"Unsupported command: {args.command}")
    outcomes = sync_taxonomy_packages(args.registry, args.install_directory)
    if not outcomes:
        print("No taxonomy packages are currently approved in the registry.")
        return 0
    for outcome in outcomes:
        print(
            f"{outcome.status}: {outcome.package_id} {outcome.version} "
            f"-> {outcome.path}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main
    raise SystemExit(main())
