from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from src.ingestion.errors import FilingPackageError
from src.ingestion.filing_packages import (
    build_filing_package,
    filing_package_sha256,
    load_filing_package_manifest,
    verify_filing_package,
)
from src.ingestion.filings import FilingMetadata


class FakePackageClient:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.json_calls: list[str] = []
        self.byte_calls: list[str] = []

    def get_json(self, url: str) -> dict:
        self.json_calls.append(url)
        return {
            "directory": {
                "item": [
                    {"name": name, "size": len(body)}
                    for name, body in self.files.items()
                ]
            }
        }

    def get_bytes(self, url: str, *, accept: str = "*/*") -> bytes:
        self.byte_calls.append(url)
        return self.files[url.rsplit("/", 1)[-1]]


def _filing() -> FilingMetadata:
    return FilingMetadata(
        cik="0000789019",
        accession_number="0001193125-25-256321",
        form="10-K",
        filing_date="2025-07-30",
        primary_document="msft-20250630.htm",
        document_url=(
            "https://www.sec.gov/Archives/edgar/data/789019/"
            "000119312525256321/msft-20250630.htm"
        ),
    )


def _taxonomy_package_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("package/META-INF/taxonomyPackage.xml", "<tp/>")
    return buffer.getvalue()


def test_build_filing_package_publishes_only_after_offline_verification(
    tmp_path: Path,
) -> None:
    files = {
        "msft-20250630.htm": b"<html>inline xbrl</html>",
        "msft-20250630.xsd": b"<schema/>",
        "msft-20250630_cal.xml": b"<linkbase/>",
        "image.jpg": b"not-xbrl",
        "exhibit.htm": b"not-primary",
    }
    client = FakePackageClient(files)
    taxonomy = tmp_path / "taxonomy.zip"
    taxonomy.write_bytes(_taxonomy_package_bytes())
    verified: list[tuple[Path, tuple[Path, ...]]] = []

    def offline_verifier(entry: Path, packages: tuple[Path, ...]) -> None:
        assert entry.read_bytes() == files["msft-20250630.htm"]
        verified.append((entry, packages))

    manifest_path = build_filing_package(
        client,
        _filing(),
        tmp_path / "filings",
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
        taxonomy_package_paths=(taxonomy,),
        offline_verifier=offline_verifier,
    )

    manifest = verify_filing_package(
        manifest_path,
        expected_accession_number=_filing().accession_number,
    )
    assert manifest.verification_status == "arelle_offline_verified"
    assert [item.relative_path for item in manifest.files] == [
        "filing/msft-20250630.htm",
        "filing/msft-20250630.xsd",
        "filing/msft-20250630_cal.xml",
    ]
    assert manifest.taxonomy_packages[0].archive_filename == "taxonomy.zip"
    assert len(verified) == 1
    assert len(filing_package_sha256(manifest_path)) == 64
    assert all("image.jpg" not in call for call in client.byte_calls)
    assert all("exhibit.htm" not in call for call in client.byte_calls)


def test_build_filing_package_reuses_verified_package(tmp_path: Path) -> None:
    files = {
        "msft-20250630.htm": b"<html/>",
        "msft-20250630.xsd": b"<schema/>",
    }
    client = FakePackageClient(files)

    def verifier(_entry: Path, _packages: tuple[Path, ...]) -> None:
        return None

    first = build_filing_package(
        client,
        _filing(),
        tmp_path,
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
        offline_verifier=verifier,
    )
    calls_after_first = (len(client.json_calls), len(client.byte_calls))
    second = build_filing_package(
        client,
        _filing(),
        tmp_path,
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
        offline_verifier=verifier,
    )

    assert second == first
    assert (len(client.json_calls), len(client.byte_calls)) == calls_after_first


def test_files_only_package_is_rejected_by_canonical_verification(tmp_path: Path) -> None:
    client = FakePackageClient({"msft-20250630.htm": b"<html/>"})
    manifest_path = build_filing_package(
        client,
        _filing(),
        tmp_path,
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
    )

    manifest = verify_filing_package(
        manifest_path,
        require_arelle_verification=False,
    )
    assert manifest.verification_status == "files_verified"
    with pytest.raises(FilingPackageError, match="offline Arelle"):
        verify_filing_package(manifest_path)


def test_verify_filing_package_rejects_modified_artifact(tmp_path: Path) -> None:
    client = FakePackageClient({"msft-20250630.htm": b"<html/>"})
    manifest_path = build_filing_package(
        client,
        _filing(),
        tmp_path,
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
    )
    manifest = load_filing_package_manifest(manifest_path)
    (manifest_path.parent / manifest.entry_document).write_bytes(b"tampered")

    with pytest.raises(FilingPackageError, match="size mismatch|hash mismatch"):
        verify_filing_package(manifest_path, require_arelle_verification=False)


def test_build_filing_package_rejects_unsafe_index_filename(tmp_path: Path) -> None:
    client = FakePackageClient(
        {
            "msft-20250630.htm": b"<html/>",
            "../extension.xsd": b"<schema/>",
        }
    )

    with pytest.raises(FilingPackageError, match="Unsafe"):
        build_filing_package(
            client,
            _filing(),
            tmp_path,
            taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
        )

    assert not list(tmp_path.rglob("manifest.json"))


def test_load_manifest_rejects_entry_path_escape(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_schema_version": 1,
                "package_policy_version": "filing-package-policy-v1",
                "cik": "0000789019",
                "accession_number": "0001193125-25-256321",
                "form": "10-K",
                "filing_date": "2025-07-30",
                "entry_document": "../outside.htm",
                "source_directory_url": "https://www.sec.gov/example",
                "taxonomy_registry_sha256": hashlib.sha256(b"registry").hexdigest(),
                "taxonomy_packages": [],
                "files": [
                    {
                        "relative_path": "../outside.htm",
                        "source_url": "https://www.sec.gov/example/outside.htm",
                        "byte_size": 1,
                        "sha256": hashlib.sha256(b"x").hexdigest(),
                    }
                ],
                "verification_status": "files_verified",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FilingPackageError, match="unsafe path"):
        verify_filing_package(manifest_path, require_arelle_verification=False)
