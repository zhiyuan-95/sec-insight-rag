from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ingestion.arelle_adapter import (
    SEC_TRANSFORM_PLUGIN_FILE_SHA256,
    SEC_TRANSFORM_PLUGIN_PATH,
    SEC_TRANSFORM_PLUGIN_REVISION,
    SEC_TRANSFORM_PLUGIN_SOURCE,
    SEC_TRANSFORM_PLUGIN_TAG,
    SEC_TRANSFORM_PLUGIN_VERSION,
    load_arelle_filing,
    verify_filing_entry_offline,
)
from src.ingestion.arelle_plugins.sec_transform import __pluginInfo__, numwordsen
from src.ingestion.errors import FilingPackageError
from src.ingestion.filing_packages import build_filing_package, load_filing_package_manifest
from src.ingestion.filings import FilingMetadata
from src.processing.arelle_records import ArelleFilingRequest


@dataclass(frozen=True)
class FakeQName:
    namespaceURI: str
    localName: str
    prefix: str | None = None


class FakeConcept:
    def __init__(self, qname: FakeQName) -> None:
        self.qname = qname
        self.typeQname = FakeQName("http://www.xbrl.org/dtr/type", "monetaryItemType")
        self.isNumeric = True
        self.isMonetary = True
        self.isShares = False
        self.isFraction = False
        self.periodType = "duration"
        self.balance = "credit"

    def label(self, **_kwargs) -> str:
        return "Operating income"

    def genLabel(self, **_kwargs) -> str:
        return "Income from operations."


class FakeContext:
    id = "D2025"
    entityIdentifier = ("http://www.sec.gov/CIK", "0000789019")
    isInstantPeriod = False
    isStartEndPeriod = True
    isForeverPeriod = False
    startDatetime = datetime(2024, 7, 1)
    endDate = date(2025, 6, 30)
    qnameDims = {}


class FakeUnit:
    measures = (
        (FakeQName("http://www.xbrl.org/2003/iso4217", "USD", "iso4217"),),
        (),
    )


class FakeFact:
    def __init__(self, qname: FakeQName, concept: FakeConcept) -> None:
        self.qname = qname
        self.concept = concept
        self.context = FakeContext()
        self.unit = FakeUnit()
        self.isNil = False
        self.xValue = 128_528_000_000
        self.value = "128528000000"
        self.decimals = "-6"
        self.precision = None
        self.sourceline = 42
        self.modelDocument = SimpleNamespace(uri=None)


class FakeRelationship:
    def __init__(self, from_concept: FakeConcept, to_concept: FakeConcept) -> None:
        self.fromModelObject = from_concept
        self.toModelObject = to_concept
        self.linkrole = "http://example.test/role/income-statement"
        self.order = 10
        self.weight = None
        self.preferredLabel = None


class FakeModel:
    def __init__(self) -> None:
        operating_qname = FakeQName(
            "https://example.test/msft/2025",
            "OperatingIncome",
            "msft",
        )
        parent_qname = FakeQName(
            "http://fasb.org/us-gaap/2025",
            "OperatingIncomeLoss",
            "us-gaap",
        )
        operating = FakeConcept(operating_qname)
        parent = FakeConcept(parent_qname)
        self.modelDocument = object()
        self.facts = [FakeFact(operating_qname, operating)]
        self.qnameConcepts = {
            operating_qname: operating,
            parent_qname: parent,
        }
        self.namespaceDocs = {
            operating_qname.namespaceURI: [],
            parent_qname.namespaceURI: [],
        }
        self.errors = []
        self._relationship = FakeRelationship(parent, operating)

    def relationshipSet(self, arcrole: str):
        if arcrole.endswith("parent-child"):
            return SimpleNamespace(modelRelationships=[self._relationship])
        return SimpleNamespace(modelRelationships=[])


class FakeSession:
    def __init__(
        self,
        *,
        successful: bool = True,
        log_level: str = "warning",
        log_code: str = "test:warning",
        log_message: str = "example",
    ) -> None:
        self.successful = successful
        self.log_level = log_level
        self.log_code = log_code
        self.log_message = log_message
        self.model = FakeModel()
        self.options = None
        self.closed = False
        self.cache_was_empty = False
        self.cache_files: tuple[str, ...] = ()

    def run(self, options, **_kwargs) -> bool:
        self.options = options
        for fact in self.model.facts:
            fact.modelDocument.uri = options.entrypointFile
        cache_directory = Path(options.cacheDirectory)
        self.cache_was_empty = cache_directory.is_dir() and not any(
            cache_directory.iterdir()
        )
        self.cache_files = tuple(
            sorted(
                path.relative_to(cache_directory).as_posix()
                for path in cache_directory.rglob("*")
                if path.is_file()
            )
        )
        return self.successful

    def get_models(self):
        return [self.model] if self.successful else []

    def get_logs(self, _format: str) -> str:
        return json.dumps(
            {
                "log": [
                    {
                        "level": self.log_level,
                        "messageCode": self.log_code,
                        "message": self.log_message,
                    }
                ]
            }
        )

    def close(self) -> None:
        self.closed = True


class FakePackageClient:
    def __init__(self) -> None:
        self.files = {
            "msft-20250630.htm": b"<html/>",
            "msft-20250630.xsd": b"<schema/>",
        }

    def get_json(self, _url: str) -> dict:
        return {
            "directory": {
                "item": [
                    {"name": name, "size": len(body)}
                    for name, body in self.files.items()
                ]
            }
        }

    def get_bytes(self, url: str, *, accept: str = "*/*") -> bytes:
        return self.files[url.rsplit("/", 1)[-1]]


def _request(tmp_path: Path) -> ArelleFilingRequest:
    filing = FilingMetadata(
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
    manifest_path = build_filing_package(
        FakePackageClient(),
        filing,
        tmp_path / "filings",
        taxonomy_registry_hash=hashlib.sha256(b"registry").hexdigest(),
        offline_verifier=lambda _entry, _packages: None,
    )
    manifest = load_filing_package_manifest(manifest_path)
    return ArelleFilingRequest(
        entry_document=str(manifest_path.parent / manifest.entry_document),
        package_manifest=str(manifest_path),
        cik=filing.cik,
        accession_number=filing.accession_number,
        form=filing.form,
        filing_date=filing.filing_date,
        fiscal_year=2025,
        fiscal_period="FY",
        sec_user_agent="Example Agent contact@example.com",
        cache_directory=str(tmp_path / "arelle-cache"),
    )


def test_load_arelle_filing_extracts_project_owned_records(tmp_path: Path) -> None:
    request = _request(tmp_path)
    session = FakeSession()

    result = load_arelle_filing(request, session_factory=lambda: session)

    assert result.status == "complete"
    assert result.accession_number == request.accession_number
    assert len(result.facts) == 1
    assert result.facts[0].concept_key.local_name == "OperatingIncome"
    assert result.facts[0].context_key.start_date == "2024-07-01"
    assert result.facts[0].unit_key is not None
    assert result.facts[0].unit_key.numerator[0].local_name == "USD"
    assert result.facts[0].source_document == "filing/msft-20250630.htm"
    assert result.facts[0].source_line == 42
    assert len(result.concepts) == 2
    assert len(result.relationships) == 1
    assert result.relationships[0].network_kind == "presentation"
    assert result.diagnostics[0].code == "test:warning"
    assert result.arelle_version is not None
    assert result.cache_state == "empty_before_taxonomy_materialization"
    assert session.options.internetConnectivity == "offline"
    assert session.options.entrypointFile == request.entry_document
    assert session.options.plugins == str(SEC_TRANSFORM_PLUGIN_PATH.resolve())
    assert session.closed is True


def test_sec_transform_plugin_is_pinned_and_converts_sec_values() -> None:
    assert SEC_TRANSFORM_PLUGIN_SOURCE == "https://github.com/Arelle/EDGAR.git"
    assert SEC_TRANSFORM_PLUGIN_TAG == "26.1.3"
    assert SEC_TRANSFORM_PLUGIN_REVISION == (
        "72033f579e89ab47e882437b5d4ceed9c7656ed5"
    )
    assert SEC_TRANSFORM_PLUGIN_VERSION == "19.2"
    assert SEC_TRANSFORM_PLUGIN_PATH.is_dir()
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SEC_TRANSFORM_PLUGIN_PATH.iterdir()
        if path.name in SEC_TRANSFORM_PLUGIN_FILE_SHA256
    } == SEC_TRANSFORM_PLUGIN_FILE_SHA256
    assert __pluginInfo__["name"] == "SEC Inline Transforms"
    assert __pluginInfo__["version"] == SEC_TRANSFORM_PLUGIN_VERSION
    assert numwordsen("No") == "0"


def test_load_arelle_filing_returns_failed_result_when_model_is_unavailable(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    session = FakeSession(successful=False)

    result = load_arelle_filing(request, session_factory=lambda: session)

    assert result.status == "failed"
    assert result.facts == ()
    assert result.diagnostics[0].severity == "fatal"
    assert session.closed is True


def test_verify_filing_entry_offline_uses_empty_offline_cache(tmp_path: Path) -> None:
    entry = tmp_path / "filing.htm"
    entry.write_text("<html/>", encoding="utf-8")
    session = FakeSession()

    verify_filing_entry_offline(
        entry,
        (),
        session_factory=lambda: session,
    )

    assert session.options.internetConnectivity == "offline"
    assert session.options.plugins == str(SEC_TRANSFORM_PLUGIN_PATH.resolve())
    assert session.cache_was_empty is True
    assert session.closed is True


def test_verify_filing_entry_offline_materializes_sec_cache_overlay(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "filing.htm"
    entry.write_text("<html/>", encoding="utf-8")
    archive = tmp_path / "cyd-2024.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cyd-2024.xsd", "<schema/>")
    session = FakeSession()

    verify_filing_entry_offline(
        entry,
        (archive,),
        session_factory=lambda: session,
    )

    assert session.cache_files == (
        "https/xbrl.sec.gov/cyd/2024/cyd-2024.xsd",
    )


def test_offline_verification_replaces_corrupt_sec_cache_file(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "filing.htm"
    entry.write_text("<html/>", encoding="utf-8")
    archive = tmp_path / "cyd-2024.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cyd-2024.xsd", "<schema/>")
    cache_file = (
        tmp_path
        / "cache"
        / "https"
        / "xbrl.sec.gov"
        / "cyd"
        / "2024"
        / "cyd-2024.xsd"
    )
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("corrupt", encoding="utf-8")

    from src.ingestion.arelle_adapter import _materialize_web_cache_archives

    _materialize_web_cache_archives((archive,), tmp_path / "cache", 100, 10_000)

    assert cache_file.read_text(encoding="utf-8") == "<schema/>"


def test_offline_verification_allows_non_dependency_validation_error(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "filing.htm"
    entry.write_text("<html/>", encoding="utf-8")
    session = FakeSession(
        log_level="error",
        log_code="ix11.11.1.2:invalidTransformation",
        log_message="Unrecognized SEC transformation namespace",
    )

    verify_filing_entry_offline(entry, (), session_factory=lambda: session)

    assert session.closed is True


def test_offline_verification_rejects_unresolved_dependency(tmp_path: Path) -> None:
    entry = tmp_path / "filing.htm"
    entry.write_text("<html/>", encoding="utf-8")
    session = FakeSession(
        log_level="error",
        log_code="IOerror",
        log_message="Could not load file while offline",
    )

    with pytest.raises(FilingPackageError, match="Could not load file"):
        verify_filing_entry_offline(entry, (), session_factory=lambda: session)

    assert session.closed is True
