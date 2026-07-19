"""Canonical offline Arelle Session adapter for Plan 203."""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from arelle import XbrlConst
from arelle.RuntimeOptions import RuntimeOptions
from arelle.Version import version as ARELLE_VERSION
from arelle.api.Session import Session
from lxml import etree

from src.ingestion.errors import FilingPackageError
from src.ingestion.filing_packages import (
    FilingPackageManifest,
    FilingPackageTaxonomy,
    verify_filing_package,
)
from src.processing.arelle_records import (
    ArelleFilingRequest,
    ArelleFilingResult,
    ArelleTimings,
    ConceptEvidence,
    ContextKey,
    DiagnosticRecord,
    DimensionValue,
    ExtractedFact,
    QNameKey,
    RelationshipEdge,
    UnitKey,
    failed_arelle_result,
)


SessionFactory = Callable[[], Any]

SEC_TRANSFORM_PLUGIN_SOURCE = "https://github.com/Arelle/EDGAR.git"
SEC_TRANSFORM_PLUGIN_TAG = "26.1.3"
SEC_TRANSFORM_PLUGIN_REVISION = "72033f579e89ab47e882437b5d4ceed9c7656ed5"
SEC_TRANSFORM_PLUGIN_VERSION = "19.2"
SEC_TRANSFORM_PLUGIN_PATH = (
    Path(__file__).resolve().parent / "arelle_plugins" / "sec_transform"
)
SEC_TRANSFORM_PLUGIN_FILE_SHA256 = {
    "__init__.py": "5a1445ba0c16da405bc20d93be9fa2d26fb2a2b99588b895deaada3f88682ce1",
    "text2num.py": "b06ef8647033055dafdebc7d33eeb99407b9ffcda56c0138ae87afe587bf800c",
}

_DEFINITION_ARCROLES = (
    XbrlConst.all,
    XbrlConst.notAll,
    XbrlConst.hypercubeDimension,
    XbrlConst.dimensionDomain,
    XbrlConst.domainMember,
    XbrlConst.dimensionDefault,
)


def load_arelle_filing(
    request: ArelleFilingRequest,
    *,
    session_factory: SessionFactory = Session,
) -> ArelleFilingResult:
    """Load one verified local package and detach all required evidence."""
    started = time.perf_counter()
    try:
        manifest = verify_filing_package(
            request.package_manifest,
            limits=request.limits,
            expected_accession_number=request.accession_number,
            require_arelle_verification=True,
        )
        entry_document = _verified_request_entry(request, manifest)
        taxonomy_paths = tuple(Path(path).resolve() for path in request.taxonomy_package_paths)
        arelle_packages, cache_archives = _verify_taxonomy_paths(
            taxonomy_paths,
            manifest.taxonomy_packages,
        )
        cache_directory = Path(request.cache_directory).resolve()
        cache_directory.mkdir(parents=True, exist_ok=True)
        cache_was_empty = not any(
            path.is_file() for path in cache_directory.rglob("*")
        )
        _materialize_web_cache_archives(
            cache_archives,
            cache_directory,
            request.limits.max_package_files,
            request.limits.max_package_bytes,
        )
        return _run_and_extract(
            request,
            entry_document,
            arelle_packages,
            cache_directory,
            session_factory=session_factory,
            started=started,
            cache_state=(
                "empty_before_taxonomy_materialization"
                if cache_was_empty
                else "preexisting_files_before_load"
            ),
        )
    except Exception as exc:
        return failed_arelle_result(
            request.accession_number,
            code="arelle_load_failed",
            message=str(exc),
            category="adapter",
        )


def verify_filing_entry_offline(
    entry_document: Path,
    taxonomy_package_paths: tuple[Path, ...],
    *,
    session_factory: SessionFactory = Session,
) -> None:
    """Prove that one staged entry document loads with an empty offline cache."""
    entry = entry_document.resolve()
    if not entry.is_file():
        raise FilingPackageError(f"Filing package entry document does not exist: {entry}")
    for package in taxonomy_package_paths:
        if not package.resolve().is_file():
            raise FilingPackageError(f"Taxonomy package does not exist: {package}")
    with tempfile.TemporaryDirectory(prefix="arelle-offline-cache-") as cache_dir:
        cache_directory = Path(cache_dir)
        arelle_packages, cache_archives = _classify_taxonomy_paths(
            taxonomy_package_paths
        )
        _materialize_web_cache_archives(
            cache_archives,
            cache_directory,
            max_files=100_000,
            max_bytes=1 * 1024 * 1024 * 1024,
        )
        session = session_factory()
        try:
            successful = session.run(
                _runtime_options(
                    entry,
                    arelle_packages,
                    cache_directory,
                    sec_user_agent="sec-insight-rag offline package verification",
                    validate=False,
                ),
                logFileName="logToBuffer",
            )
            models = session.get_models()
            diagnostics = _session_diagnostics(session)
            blocking = [item for item in diagnostics if _is_dependency_diagnostic(item)]
            if not successful or not models or not _model_loaded(models[-1]) or blocking:
                detail = diagnostics[0].message if diagnostics else "Arelle returned no loaded model"
                if blocking:
                    detail = blocking[0].message
                raise FilingPackageError(
                    f"Offline Arelle verification failed for {entry.name}: {detail}"
                )
        finally:
            session.close()


def _run_and_extract(
    request: ArelleFilingRequest,
    entry_document: Path,
    taxonomy_paths: tuple[Path, ...],
    cache_directory: Path,
    *,
    session_factory: SessionFactory,
    started: float,
    cache_state: str,
) -> ArelleFilingResult:
    session = session_factory()
    load_started = time.perf_counter()
    try:
        successful = session.run(
            _runtime_options(
                entry_document,
                taxonomy_paths,
                cache_directory,
                sec_user_agent=request.sec_user_agent,
                validate=request.validation_profile != "none",
            ),
            logFileName="logToBuffer",
        )
        load_finished = time.perf_counter()
        models = session.get_models()
        if not successful or not models or not _model_loaded(models[-1]):
            diagnostics = _bounded_diagnostics(
                _session_diagnostics(session),
                request.limits.max_diagnostics,
            )
            message = (
                diagnostics[0].message
                if diagnostics
                else "Arelle did not return a loaded XBRL model"
            )
            return failed_arelle_result(
                request.accession_number,
                code="arelle_model_unavailable",
                message=message,
                category="load",
            )

        model_xbrl = models[-1]
        extraction_started = time.perf_counter()
        facts = _extract_facts(model_xbrl, request)
        reported_concepts = {fact.concept_key for fact in facts}
        relationships, relationship_truncated = _extract_relationships(
            model_xbrl,
            reported_concepts,
            request.limits.max_relationships,
        )
        evidence_keys = set(reported_concepts)
        for relationship in relationships:
            evidence_keys.add(relationship.from_concept)
            evidence_keys.add(relationship.to_concept)
        concepts = _extract_concepts(model_xbrl, evidence_keys, request.limits.max_concepts)
        diagnostics = list(_session_diagnostics(session))
        logged_codes = {item.code for item in diagnostics}
        diagnostics.extend(
            item
            for item in _model_diagnostics(model_xbrl)
            if item.code not in logged_codes
        )
        if relationship_truncated:
            diagnostics.append(
                DiagnosticRecord(
                    category="resource",
                    severity="error",
                    code="relationship_limit_exceeded",
                    message=(
                        "Relationship extraction exceeded "
                        f"{request.limits.max_relationships} edges"
                    ),
                    source_document=str(entry_document),
                )
            )
        bounded_diagnostics, diagnostics_truncated = _bounded_diagnostics_with_state(
            diagnostics,
            request.limits.max_diagnostics,
        )
        extraction_finished = time.perf_counter()
        status = "degraded" if relationship_truncated or diagnostics_truncated else "complete"
        if any(item.severity in {"error", "fatal"} for item in bounded_diagnostics):
            status = "degraded"
        namespaces = tuple(sorted(_model_namespaces(model_xbrl)))
        return ArelleFilingResult(
            accession_number=request.accession_number,
            status=status,
            cik=request.cik,
            form=request.form,
            filing_date=request.filing_date,
            fiscal_year=request.fiscal_year,
            fiscal_period=request.fiscal_period,
            facts=facts,
            concepts=concepts,
            relationships=relationships,
            diagnostics=bounded_diagnostics,
            namespaces=namespaces,
            timings=ArelleTimings(
                load_seconds=load_finished - load_started,
                validation_seconds=0.0,
                extraction_seconds=extraction_finished - extraction_started,
                total_seconds=extraction_finished - started,
            ),
            cache_state=cache_state,
            arelle_version=str(ARELLE_VERSION),
        )
    except _ResourceLimitExceeded as exc:
        return failed_arelle_result(
            request.accession_number,
            code=exc.code,
            message=str(exc),
            category="resource",
        )
    finally:
        session.close()


def _runtime_options(
    entry_document: Path,
    taxonomy_paths: Sequence[Path],
    cache_directory: Path,
    *,
    sec_user_agent: str,
    validate: bool,
) -> RuntimeOptions:
    return RuntimeOptions(
        entrypointFile=str(entry_document),
        packages=[str(path) for path in taxonomy_paths] or None,
        plugins=str(_verified_sec_transform_plugin_path()),
        internetConnectivity="offline",
        cacheDirectory=str(cache_directory),
        httpUserAgent=sec_user_agent,
        validate=validate,
        keepOpen=True,
        disablePersistentConfig=True,
        logFile="logToBuffer",
        logLevel="INFO",
    )


def _verified_sec_transform_plugin_path() -> Path:
    plugin_path = SEC_TRANSFORM_PLUGIN_PATH.resolve()
    missing = [
        filename
        for filename in SEC_TRANSFORM_PLUGIN_FILE_SHA256
        if not (plugin_path / filename).is_file()
    ]
    if missing:
        raise FilingPackageError(
            "Pinned SEC Inline Transforms plugin is incomplete: "
            + ", ".join(missing)
        )
    mismatched = [
        filename
        for filename, expected_sha256 in SEC_TRANSFORM_PLUGIN_FILE_SHA256.items()
        if _sha256_file(plugin_path / filename) != expected_sha256
    ]
    if mismatched:
        raise FilingPackageError(
            "Pinned SEC Inline Transforms plugin hash mismatch: "
            + ", ".join(mismatched)
        )
    return plugin_path


def _verified_request_entry(
    request: ArelleFilingRequest,
    manifest: FilingPackageManifest,
) -> Path:
    entry_document = Path(request.entry_document).resolve()
    expected = (Path(request.package_manifest).resolve().parent / manifest.entry_document).resolve()
    if entry_document != expected:
        raise FilingPackageError("Arelle request entry document does not match its manifest")
    if not entry_document.is_file():
        raise FilingPackageError("Arelle request entry document does not exist")
    return entry_document


def _verify_taxonomy_paths(
    paths: tuple[Path, ...],
    records: tuple[FilingPackageTaxonomy, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    if len(paths) != len(records):
        raise FilingPackageError("Arelle request taxonomy package count does not match manifest")
    by_name = {path.name: path for path in paths}
    if len(by_name) != len(paths):
        raise FilingPackageError("Arelle request taxonomy package names are ambiguous")
    for record in records:
        path = by_name.get(record.archive_filename)
        if path is None or not path.is_file():
            raise FilingPackageError(
                f"Manifest taxonomy package is unavailable: {record.archive_filename}"
            )
        if path.stat().st_size != record.byte_size or _sha256_file(path) != record.sha256:
            raise FilingPackageError(
                f"Manifest taxonomy package does not match: {record.archive_filename}"
            )
        from src.ingestion.taxonomy_packages import taxonomy_archive_install_mode

        actual_mode = taxonomy_archive_install_mode(path)
        if actual_mode != record.install_mode:
            raise FilingPackageError(
                f"Manifest taxonomy package mode does not match: {record.archive_filename}"
            )
    return _split_taxonomy_paths(paths, records)


def _classify_taxonomy_paths(
    paths: tuple[Path, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    from src.ingestion.taxonomy_packages import taxonomy_archive_install_mode

    arelle_packages: list[Path] = []
    cache_archives: list[Path] = []
    for path in paths:
        mode = taxonomy_archive_install_mode(path)
        if mode == "arelle_package":
            arelle_packages.append(path)
        else:
            cache_archives.append(path)
    return tuple(arelle_packages), tuple(cache_archives)


def _split_taxonomy_paths(
    paths: tuple[Path, ...],
    records: tuple[FilingPackageTaxonomy, ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    mode_by_name = {record.archive_filename: record.install_mode for record in records}
    return (
        tuple(path for path in paths if mode_by_name[path.name] == "arelle_package"),
        tuple(
            path
            for path in paths
            if mode_by_name[path.name] in {"web_cache_archive", "web_cache_overlay"}
        ),
    )


def _materialize_web_cache_archives(
    archives: tuple[Path, ...],
    cache_directory: Path,
    max_files: int,
    max_bytes: int,
) -> None:
    file_count = 0
    total_bytes = 0
    cache_root = cache_directory.resolve()
    for archive in archives:
        from src.ingestion.taxonomy_packages import taxonomy_archive_install_mode

        install_mode = taxonomy_archive_install_mode(archive)
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if member.is_dir():
                    continue
                relative = _sec_cache_relative_path(
                    member.filename,
                    archive=archive,
                    install_mode=install_mode,
                )
                file_count += 1
                total_bytes += member.file_size
                if file_count > max_files or total_bytes > max_bytes:
                    raise FilingPackageError(
                        "Taxonomy web-cache archive exceeded the resource policy"
                    )
                target = (cache_root / "https" / relative).resolve()
                try:
                    target.relative_to(cache_root)
                except ValueError as exc:
                    raise FilingPackageError(
                        "Taxonomy cache archive escaped the cache directory"
                    ) from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and _zip_member_matches(target, member):
                    continue
                temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
                try:
                    with zipped.open(member) as source, temporary.open("wb") as output:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                    if not _zip_member_matches(temporary, member):
                        raise FilingPackageError(
                            f"Taxonomy cache extraction mismatch: {member.filename}"
                        )
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()


def _zip_member_matches(path: Path, member: zipfile.ZipInfo) -> bool:
    if path.stat().st_size != member.file_size:
        return False
    checksum = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            checksum = zipfile.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF == member.CRC


def _sec_cache_relative_path(
    value: str,
    *,
    archive: Path,
    install_mode: str,
) -> Path:
    normalized = value.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if install_mode == "web_cache_overlay":
        stem = archive.name.removesuffix(".zip")
        if "-" not in stem or len(parts) != 1:
            raise FilingPackageError(f"Unsafe SEC taxonomy overlay path: {value}")
        taxonomy_name, version = stem.rsplit("-", 1)
        if (
            not taxonomy_name
            or not version[:4].isdigit()
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise FilingPackageError(f"Unsafe SEC taxonomy overlay path: {value}")
        return Path("xbrl.sec.gov", taxonomy_name, version, *parts)
    if len(parts) >= 3 and parts[0].lower() == "xbrl.sec.gov":
        if any(part in {"", ".", ".."} for part in parts):
            raise FilingPackageError(f"Unsafe SEC taxonomy cache path: {value}")
        return Path(*parts)
    if (
        len(parts) < 3
        or not parts[0][:4].isdigit()
        or parts[1].lower() != "xbrl.sec.gov"
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise FilingPackageError(f"Unsafe SEC taxonomy cache path: {value}")
    return Path(*parts[1:])


def _extract_facts(
    model_xbrl: Any,
    request: ArelleFilingRequest,
) -> tuple[ExtractedFact, ...]:
    facts: list[ExtractedFact] = []
    for model_fact in getattr(model_xbrl, "facts", ()):
        if len(facts) >= request.limits.max_facts:
            raise _ResourceLimitExceeded(
                "fact_limit_exceeded",
                f"Arelle model exceeded {request.limits.max_facts} facts",
            )
        qname = getattr(model_fact, "qname", None)
        context = getattr(model_fact, "context", None)
        if qname is None or context is None:
            continue
        nil = bool(getattr(model_fact, "isNil", False))
        x_value = None if nil else getattr(model_fact, "xValue", None)
        raw_value = None if nil else getattr(model_fact, "value", None)
        unit = getattr(model_fact, "unit", None)
        facts.append(
            ExtractedFact(
                concept_key=_qname_key(qname),
                context_key=_context_key(context),
                value=_string_or_none(x_value),
                value_raw=_string_or_none(raw_value),
                nil=nil,
                unit_key=_unit_key(unit) if unit is not None else None,
                decimals=_string_or_none(getattr(model_fact, "decimals", None)),
                precision=_string_or_none(getattr(model_fact, "precision", None)),
                source_document=_fact_source_document(
                    model_fact,
                    Path(request.package_manifest).resolve().parent,
                ),
                source_line=_int_or_none(getattr(model_fact, "sourceline", None)),
            )
        )
    return tuple(facts)


def _fact_source_document(model_fact: Any, package_root: Path) -> str | None:
    model_document = getattr(model_fact, "modelDocument", None)
    uri = _string_or_none(getattr(model_document, "uri", None))
    if uri is None:
        return None
    if uri.startswith(("http://", "https://")):
        return uri
    try:
        source = Path(uri).resolve()
        return source.relative_to(package_root).as_posix()
    except (OSError, ValueError):
        return Path(uri).name or uri


def _extract_concepts(
    model_xbrl: Any,
    concept_keys: set[QNameKey],
    max_concepts: int,
) -> tuple[ConceptEvidence, ...]:
    concepts_by_key: dict[QNameKey, ConceptEvidence] = {}
    qname_concepts = getattr(model_xbrl, "qnameConcepts", {})
    for qname, concept in getattr(qname_concepts, "items", lambda: ())():
        key = _qname_key(qname)
        if key not in concept_keys:
            continue
        if len(concepts_by_key) >= max_concepts:
            raise _ResourceLimitExceeded(
                "concept_limit_exceeded",
                f"Arelle result exceeded {max_concepts} relevant concepts",
            )
        concepts_by_key[key] = _concept_evidence(concept, key)
    return tuple(concepts_by_key[key] for key in sorted(concepts_by_key))


def _concept_evidence(concept: Any, key: QNameKey) -> ConceptEvidence:
    label = _safe_concept_label(concept, documentation=False)
    documentation = _safe_concept_label(concept, documentation=True)
    type_qname = getattr(concept, "typeQname", None)
    return ConceptEvidence(
        concept_key=key,
        standard_label=label,
        documentation=documentation,
        type_key=_qname_key(type_qname) if type_qname is not None else None,
        is_numeric=bool(getattr(concept, "isNumeric", False)),
        numeric_kind=_numeric_kind(concept),
        period_type=_string_or_none(getattr(concept, "periodType", None)),
        balance=_string_or_none(getattr(concept, "balance", None)),
    )


def _extract_relationships(
    model_xbrl: Any,
    reported_concepts: set[QNameKey],
    max_relationships: int,
) -> tuple[tuple[RelationshipEdge, ...], bool]:
    edges: dict[tuple[Any, ...], RelationshipEdge] = {}
    networks = (
        ("presentation", (XbrlConst.parentChild,)),
        ("calculation", (XbrlConst.summationItem,)),
        ("definition", _DEFINITION_ARCROLES),
    )
    for network_kind, arcroles in networks:
        for arcrole in arcroles:
            relationship_set = model_xbrl.relationshipSet(arcrole)
            for relationship in getattr(relationship_set, "modelRelationships", ()):
                from_qname = getattr(
                    getattr(relationship, "fromModelObject", None), "qname", None
                )
                to_qname = getattr(
                    getattr(relationship, "toModelObject", None), "qname", None
                )
                if from_qname is None or to_qname is None:
                    continue
                from_key = _qname_key(from_qname)
                to_key = _qname_key(to_qname)
                if from_key not in reported_concepts and to_key not in reported_concepts:
                    continue
                edge = RelationshipEdge(
                    network_kind=network_kind,
                    link_role=str(getattr(relationship, "linkrole", "") or ""),
                    from_concept=from_key,
                    to_concept=to_key,
                    order=_string_or_none(getattr(relationship, "order", None)),
                    weight=_string_or_none(getattr(relationship, "weight", None)),
                    preferred_label=_string_or_none(
                        getattr(relationship, "preferredLabel", None)
                    ),
                )
                identity = (
                    edge.network_kind,
                    edge.link_role,
                    edge.from_concept,
                    edge.to_concept,
                    edge.order,
                    edge.weight,
                    edge.preferred_label,
                )
                edges[identity] = edge
                if len(edges) > max_relationships:
                    kept = tuple(sorted(edges.values(), key=_relationship_sort_key))[
                        :max_relationships
                    ]
                    return kept, True
    return tuple(sorted(edges.values(), key=_relationship_sort_key)), False


def _context_key(context: Any) -> ContextKey:
    entity_scheme, entity_identifier = getattr(context, "entityIdentifier", ("", ""))
    if bool(getattr(context, "isInstantPeriod", False)):
        period_type = "instant"
        start_date = None
        end_date = None
        instant_date = _date_text(getattr(context, "instantDate", None))
    elif bool(getattr(context, "isStartEndPeriod", False)):
        period_type = "duration"
        start_date = _date_text(getattr(context, "startDatetime", None))
        end_date = _date_text(getattr(context, "endDate", None))
        instant_date = None
    elif bool(getattr(context, "isForeverPeriod", False)):
        period_type = "forever"
        start_date = end_date = instant_date = None
    else:
        period_type = "unknown"
        start_date = end_date = instant_date = None
    dimensions = tuple(
        sorted(
            (
                _dimension_value(dimension_qname, dimension)
                for dimension_qname, dimension in getattr(
                    context, "qnameDims", {}
                ).items()
            ),
            key=lambda item: item.dimension,
        )
    )
    return ContextKey(
        context_id=_string_or_none(getattr(context, "id", None)),
        entity_scheme=str(entity_scheme or ""),
        entity_identifier=str(entity_identifier or ""),
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
        instant_date=instant_date,
        dimensions=dimensions,
    )


def _dimension_value(dimension_qname: Any, dimension: Any) -> DimensionValue:
    if bool(getattr(dimension, "isExplicit", False)):
        return DimensionValue(
            dimension=_qname_key(dimension_qname),
            member=_qname_key(getattr(dimension, "memberQname")),
        )
    typed_member = getattr(dimension, "typedMember", None)
    return DimensionValue(
        dimension=_qname_key(dimension_qname),
        typed_member_xml=_canonical_typed_member(typed_member),
    )


def _unit_key(unit: Any) -> UnitKey:
    numerator, denominator = getattr(unit, "measures", ((), ()))
    return UnitKey(
        numerator=tuple(sorted((_qname_key(item) for item in numerator))),
        denominator=tuple(sorted((_qname_key(item) for item in denominator))),
    )


def _qname_key(qname: Any) -> QNameKey:
    return QNameKey(
        namespace_uri=str(getattr(qname, "namespaceURI", "") or ""),
        local_name=str(getattr(qname, "localName", "") or ""),
        prefix=_string_or_none(getattr(qname, "prefix", None)),
    )


def _model_diagnostics(model_xbrl: Any) -> tuple[DiagnosticRecord, ...]:
    return tuple(
        DiagnosticRecord(
            category="validation",
            severity="error",
            code=str(error),
            message=str(error),
        )
        for error in getattr(model_xbrl, "errors", ())
    )


def _session_diagnostics(session: Any) -> tuple[DiagnosticRecord, ...]:
    try:
        raw = session.get_logs("json")
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if isinstance(value, dict):
        messages = value.get("log", value.get("messages", []))
    else:
        messages = value
    if not isinstance(messages, list):
        return ()
    diagnostics: list[DiagnosticRecord] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level", item.get("levelname", "info"))).lower()
        message_value = item.get("message", item.get("formattedMessage", item))
        if isinstance(message_value, dict):
            message_value = message_value.get("text", message_value)
        diagnostics.append(
            DiagnosticRecord(
                category="arelle_log",
                severity=_diagnostic_severity(level),
                code=str(item.get("messageCode", item.get("code", "arelle"))),
                message=str(message_value),
                source_document=_string_or_none(item.get("file")),
            )
        )
    return tuple(diagnostics)


def _bounded_diagnostics(
    diagnostics: Iterable[DiagnosticRecord],
    maximum: int,
) -> tuple[DiagnosticRecord, ...]:
    return _bounded_diagnostics_with_state(diagnostics, maximum)[0]


def _bounded_diagnostics_with_state(
    diagnostics: Iterable[DiagnosticRecord],
    maximum: int,
) -> tuple[tuple[DiagnosticRecord, ...], bool]:
    items: list[DiagnosticRecord] = []
    seen: set[tuple[Any, ...]] = set()
    for item in diagnostics:
        identity = (
            item.category,
            item.severity,
            item.code,
            item.message,
            item.concept_key,
            item.context_id,
            item.source_document,
        )
        if identity in seen:
            continue
        seen.add(identity)
        items.append(item)
    if len(items) <= maximum:
        return tuple(items), False
    kept = items[: max(0, maximum - 1)]
    kept.append(
        DiagnosticRecord(
            category="resource",
            severity="error",
            code="diagnostic_limit_exceeded",
            message=f"Diagnostics were truncated from {len(items)} to {maximum}",
        )
    )
    return tuple(kept), True


def _model_namespaces(model_xbrl: Any) -> set[str]:
    namespaces = getattr(model_xbrl, "namespaceDocs", {})
    if hasattr(namespaces, "keys"):
        return {str(item) for item in namespaces.keys() if str(item)}
    return set()


def _model_loaded(model_xbrl: Any) -> bool:
    return getattr(model_xbrl, "modelDocument", None) is not None


def _safe_concept_label(concept: Any, *, documentation: bool) -> str | None:
    try:
        if documentation:
            return _string_or_none(
                concept.genLabel(
                    role=XbrlConst.documentationLabel,
                    lang="en",
                    strip=True,
                )
            )
        return _string_or_none(concept.label(lang="en", strip=True))
    except (AttributeError, TypeError, ValueError):
        return None


def _numeric_kind(concept: Any) -> str | None:
    if bool(getattr(concept, "isMonetary", False)):
        return "monetary"
    if bool(getattr(concept, "isShares", False)):
        return "shares"
    if bool(getattr(concept, "isFraction", False)):
        return "fraction"
    if bool(getattr(concept, "isNumeric", False)):
        return "numeric"
    return None


def _canonical_typed_member(value: Any) -> str:
    if value is None:
        return "<missing/>"
    try:
        return etree.tostring(value, method="c14n", with_comments=False).decode("utf-8")
    except (TypeError, ValueError):
        return str(
            getattr(value, "xValue", None)
            or getattr(value, "stringValue", None)
            or value
        )


def _diagnostic_severity(level: str) -> str:
    if level in {"fatal", "critical"}:
        return "fatal"
    if level == "error":
        return "error"
    if level in {"warning", "warn"}:
        return "warning"
    return "info"


def _is_dependency_diagnostic(diagnostic: DiagnosticRecord) -> bool:
    code = diagnostic.code.casefold()
    message = diagnostic.message.casefold()
    return (
        code in {"ioerror", "filenotloadable", "filenotfound"}
        or "could not load file" in message
        or "attempt to download" in message
        or "attempted download" in message
        or "unresolved dependency" in message
    )


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    date_method = getattr(value, "date", None)
    normalized = date_method() if callable(date_method) else value
    isoformat = getattr(normalized, "isoformat", None)
    return str(isoformat() if callable(isoformat) else normalized)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _relationship_sort_key(edge: RelationshipEdge) -> tuple[Any, ...]:
    return (
        edge.network_kind,
        edge.link_role,
        edge.from_concept,
        edge.to_concept,
        edge.order or "",
        edge.weight or "",
    )


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ResourceLimitExceeded(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
