"""Project-owned serializable records for one Arelle filing result."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from hashlib import sha256
from typing import Any, ClassVar

ARELLE_RESULT_COMPLETE = "complete"
ARELLE_RESULT_FAILED = "failed"
ARELLE_RESULT_SCHEMA_VERSION = "2"
ARELLE_ADAPTER_VERSION = "1"


@dataclass(frozen=True)
class ArelleFilingRequest:
    """Inputs required to process one locally acquired filing accession."""

    cik: str
    accession_number: str
    form: str
    filing_date: str
    entry_point_path: str
    source_url: str | None
    content_sha256: str | None
    sec_user_agent: str | None = None
    local_dependency_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArelleFilingIdentity:
    """Serializable filing identity retained in every result envelope."""

    cik: str
    accession_number: str
    form: str
    filing_date: str
    entry_point_path: str
    source_url: str | None


@dataclass(frozen=True)
class ArelleDimensionRecord:
    dimension: str
    member: str
    is_typed: bool


@dataclass(frozen=True)
class ArelleFactRecord:
    evidence_id: str
    concept_id: str
    context_id: str | None
    unit_id: str | None
    display_value: str | None
    numeric_value: str | None
    is_nil: bool
    decimals: str | None
    precision: str | None
    xml_lang: str | None


@dataclass(frozen=True)
class ArelleConceptRecord:
    evidence_id: str
    qname: str
    namespace_uri: str
    local_name: str
    prefix: str | None
    label: str | None
    documentation: str | None
    type_qname: str | None
    base_type: str | None
    period_type: str | None
    balance: str | None
    is_numeric: bool
    is_abstract: bool
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArelleContextRecord:
    context_id: str
    entity_scheme: str | None
    entity_identifier: str | None
    period_type: str
    start_date: str | None
    end_date: str | None
    instant_date: str | None
    dimensions: tuple[ArelleDimensionRecord, ...] = ()


@dataclass(frozen=True)
class ArelleUnitRecord:
    unit_id: str
    numerator_measures: tuple[str, ...]
    denominator_measures: tuple[str, ...]


@dataclass(frozen=True)
class ArelleRelationshipRecord:
    evidence_id: str
    network_kind: str
    arcrole: str
    link_role: str | None
    from_id: str
    to_id: str
    order: str | None
    weight: str | None
    preferred_label: str | None
    target_role: str | None


@dataclass(frozen=True)
class ArelleFormulaAssertionRecord:
    assertion_id: str
    assertion_type: str
    satisfied_count: int
    unsatisfied_count: int
    ok_message_count: int
    warning_message_count: int
    error_message_count: int


@dataclass(frozen=True)
class ArelleDiagnosticRecord:
    severity: str
    code: str
    message: str
    fact_ids: tuple[str, ...] = ()
    relationship_ids: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArelleNamespaceRecord:
    prefix: str | None
    namespace_uri: str


@dataclass(frozen=True)
class ArelleSourceDocumentRecord:
    uri: str
    local_path: str | None
    document_type: str
    target_namespace: str | None
    content_sha256: str | None


@dataclass(frozen=True)
class ArelleRecordCounts:
    facts: int = 0
    concepts: int = 0
    contexts: int = 0
    units: int = 0
    relationships: int = 0
    formula_assertions: int = 0
    diagnostics: int = 0
    source_documents: int = 0


@dataclass(frozen=True)
class ArelleTimingRecord:
    load_validate_seconds: float = 0.0
    extraction_seconds: float = 0.0
    total_seconds: float = 0.0


@dataclass(frozen=True)
class ArelleFilingResult:
    """Complete or failed project-owned evidence envelope for one accession."""

    schema_version: str
    adapter_version: str
    arelle_version: str
    filing: ArelleFilingIdentity
    status: str
    facts: tuple[ArelleFactRecord, ...]
    concepts: tuple[ArelleConceptRecord, ...]
    contexts: tuple[ArelleContextRecord, ...]
    units: tuple[ArelleUnitRecord, ...]
    relationships: tuple[ArelleRelationshipRecord, ...]
    formula_assertions: tuple[ArelleFormulaAssertionRecord, ...]
    diagnostics: tuple[ArelleDiagnosticRecord, ...]
    namespaces: tuple[ArelleNamespaceRecord, ...]
    source_documents: tuple[ArelleSourceDocumentRecord, ...]
    record_counts: ArelleRecordCounts
    timings: ArelleTimingRecord
    content_sha256: str | None
    payload_sha256: str
    worker_pid: int | None
    session_closed: bool

    _RECORD_TYPES: ClassVar[dict[str, type[Any]]]

    def to_json(self) -> str:
        """Return the canonical JSON representation of this result."""
        return _canonical_json(_encode_record(self))

    @classmethod
    def from_json(cls, payload: str) -> ArelleFilingResult:
        """Decode and verify one canonical result payload."""
        decoded = _decode_record(json.loads(payload))
        if not isinstance(decoded, cls):
            raise ValueError("Arelle payload was not a filing result")
        expected_hash = _result_hash(replace(decoded, payload_sha256=""))
        if decoded.payload_sha256 != expected_hash:
            raise ValueError("Arelle result payload hash did not match")
        return decoded


_SERIALIZABLE_RECORD_TYPES = (
    ArelleFilingIdentity,
    ArelleDimensionRecord,
    ArelleFactRecord,
    ArelleConceptRecord,
    ArelleContextRecord,
    ArelleUnitRecord,
    ArelleRelationshipRecord,
    ArelleFormulaAssertionRecord,
    ArelleDiagnosticRecord,
    ArelleNamespaceRecord,
    ArelleSourceDocumentRecord,
    ArelleRecordCounts,
    ArelleTimingRecord,
    ArelleFilingResult,
)
ArelleFilingResult._RECORD_TYPES = {
    record_type.__name__: record_type for record_type in _SERIALIZABLE_RECORD_TYPES
}


def finalize_arelle_result(result: ArelleFilingResult) -> ArelleFilingResult:
    """Return a result with its canonical payload hash populated."""
    without_hash = replace(result, payload_sha256="")
    return replace(without_hash, payload_sha256=_result_hash(without_hash))


def failed_arelle_result(
    request: ArelleFilingRequest,
    *,
    arelle_version: str,
    diagnostic: ArelleDiagnosticRecord,
    worker_pid: int | None,
    session_closed: bool,
    total_seconds: float,
) -> ArelleFilingResult:
    """Build a canonical failed result without exposing partial evidence."""
    return finalize_arelle_result(
        ArelleFilingResult(
            schema_version=ARELLE_RESULT_SCHEMA_VERSION,
            adapter_version=ARELLE_ADAPTER_VERSION,
            arelle_version=arelle_version,
            filing=ArelleFilingIdentity(
                cik=request.cik,
                accession_number=request.accession_number,
                form=request.form,
                filing_date=request.filing_date,
                entry_point_path=request.entry_point_path,
                source_url=request.source_url,
            ),
            status=ARELLE_RESULT_FAILED,
            facts=(),
            concepts=(),
            contexts=(),
            units=(),
            relationships=(),
            formula_assertions=(),
            diagnostics=(diagnostic,),
            namespaces=(),
            source_documents=(),
            record_counts=ArelleRecordCounts(diagnostics=1),
            timings=ArelleTimingRecord(total_seconds=total_seconds),
            content_sha256=request.content_sha256,
            payload_sha256="",
            worker_pid=worker_pid,
            session_closed=session_closed,
        )
    )


def _result_hash(result: ArelleFilingResult) -> str:
    return sha256(_canonical_json(_encode_record(result)).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _encode_record(value: Any) -> Any:
    if is_dataclass(value):
        return {
            "__record__": value.__class__.__name__,
            **{
                field.name: _encode_record(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, tuple):
        return {"__tuple__": [_encode_record(item) for item in value]}
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    raise TypeError(f"Arelle result contained a non-serializable value: {type(value).__name__}")


def _decode_record(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_record(item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"__tuple__"}:
        items = value["__tuple__"]
        if not isinstance(items, list):
            raise ValueError("Arelle tuple payload was malformed")
        return tuple(_decode_record(item) for item in items)
    record_name = value.get("__record__")
    if not isinstance(record_name, str):
        raise ValueError("Arelle record payload was malformed")
    record_type = ArelleFilingResult._RECORD_TYPES.get(record_name)
    if record_type is None:
        raise ValueError(f"Unknown Arelle record type: {record_name}")
    return record_type(
        **{
            key: _decode_record(item)
            for key, item in value.items()
            if key != "__record__"
        }
    )
