from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from src.ingestion.errors import TaxonomyPackageError
from src.ingestion.taxonomy_packages import (
    installed_taxonomy_package_paths,
    load_taxonomy_package_registry,
    main,
    sync_taxonomy_packages,
    taxonomy_archive_install_mode,
    taxonomy_registry_sha256,
)


def _taxonomy_package_bytes(content: bytes = b"taxonomy") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("package/META-INF/taxonomyPackage.xml", b"<tp/>" + content)
    return buffer.getvalue()


_PACKAGE_BYTES = _taxonomy_package_bytes()


def _write_registry(
    path: Path,
    *,
    package_bytes: bytes | None = _PACKAGE_BYTES,
    source_url: str = "https://xbrl.example.test/packages/us-gaap.zip",
    archive_filename: str = "us-gaap-2025.zip",
) -> None:
    packages = []
    if package_bytes is not None:
        packages.append(
            {
                "package_id": "us-gaap",
                "version": "2025",
                "source_url": source_url,
                "approved_redirect_hosts": ["downloads.example.test"],
                "archive_filename": archive_filename,
                "install_mode": "arelle_package",
                "byte_size": len(package_bytes),
                "sha256": hashlib.sha256(package_bytes).hexdigest(),
                "namespaces": ["https://xbrl.fasb.org/us-gaap/2025"],
                "catalog_remappings": {
                    "https://xbrl.fasb.org/us-gaap/2025/": "taxonomy/us-gaap/2025/"
                },
                "compatible_arelle": ">=2.41,<3.0",
                "approval_date": "2026-07-17",
            }
        )
    path.write_text(
        json.dumps(
            {
                "registry_schema_version": 1,
                "registry_policy_version": "taxonomy-registry-v1",
                "packages": packages,
            }
        ),
        encoding="utf-8",
    )


def test_source_registry_is_valid_and_safe_by_default() -> None:
    registry = load_taxonomy_package_registry("data/taxonomy_packages.json")

    assert registry.registry_policy_version == "taxonomy-registry-v1"
    assert [(item.package_id, item.install_mode) for item in registry.packages] == [
        ("fasb-us-gaap", "arelle_package"),
        ("fasb-srt", "arelle_package"),
        ("sec-standard-taxonomies", "web_cache_archive"),
        ("sec-cyd", "web_cache_overlay"),
        ("fasb-us-gaap", "arelle_package"),
        ("fasb-srt", "arelle_package"),
        ("sec-standard-taxonomies", "web_cache_archive"),
    ]
    assert len(taxonomy_registry_sha256("data/taxonomy_packages.json")) == 64


def test_sync_installs_then_reuses_exact_verified_package(tmp_path: Path) -> None:
    package_bytes = _taxonomy_package_bytes(b"installed")
    registry_path = tmp_path / "registry.json"
    install_dir = tmp_path / "installed"
    _write_registry(registry_path, package_bytes=package_bytes)
    calls: list[str] = []

    def downloader(entry, target: Path) -> None:
        calls.append(entry.package_id)
        target.write_bytes(package_bytes)

    first = sync_taxonomy_packages(registry_path, install_dir, downloader=downloader)
    second = sync_taxonomy_packages(registry_path, install_dir, downloader=downloader)

    assert [outcome.status for outcome in first] == ["installed"]
    assert [outcome.status for outcome in second] == ["reused"]
    assert calls == ["us-gaap"]
    assert first[0].path.read_bytes() == package_bytes
    assert installed_taxonomy_package_paths(registry_path, install_dir) == (
        first[0].path,
    )


def test_sync_rejects_hash_mismatch_without_publishing_file(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    install_dir = tmp_path / "installed"
    _write_registry(registry_path, package_bytes=_taxonomy_package_bytes(b"expected"))

    def downloader(_entry, target: Path) -> None:
        target.write_bytes(b"unexpected")

    with pytest.raises(TaxonomyPackageError, match="size mismatch|hash mismatch"):
        sync_taxonomy_packages(registry_path, install_dir, downloader=downloader)

    assert not (install_dir / "us-gaap-2025.zip").exists()
    assert list(install_dir.glob("*.part")) == []


@pytest.mark.parametrize(
    ("source_url", "archive_filename", "message"),
    [
        ("http://xbrl.example.test/package.zip", "package.zip", "HTTPS"),
        ("https://xbrl.example.test/package.zip", "../package.zip", "safe"),
    ],
)
def test_registry_rejects_unapproved_transport_or_unsafe_filename(
    tmp_path: Path,
    source_url: str,
    archive_filename: str,
    message: str,
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        source_url=source_url,
        archive_filename=archive_filename,
    )

    with pytest.raises(TaxonomyPackageError, match=message):
        load_taxonomy_package_registry(registry_path)


def test_empty_registry_cli_reports_no_approved_packages(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, package_bytes=None)

    exit_code = main(
        [
            "sync",
            "--registry",
            str(registry_path),
            "--install-directory",
            str(tmp_path / "installed"),
        ]
    )

    assert exit_code == 0
    assert "No taxonomy packages" in capsys.readouterr().out


def test_sec_taxonomy_overlay_archive_is_classified(tmp_path: Path) -> None:
    archive = tmp_path / "cyd-2024.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cyd-2024.xsd", "<schema/>")

    assert taxonomy_archive_install_mode(archive) == "web_cache_overlay"
