"""Bounded JSON codec for worker-to-parent Arelle results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from src.processing.arelle_records import (
    ARELLE_RESULT_SCHEMA_VERSION,
    ArelleFilingResult,
    ArelleRecordCounts,
    ArelleTimings,
    ConceptEvidence,
    ContextKey,
    DiagnosticRecord,
    DimensionValue,
    ExtractedFact,
    QNameKey,
    RelationshipEdge,
    UnitKey,
)
from src.processing.errors import InlineXbrlExtractionError


_ENVELOPE_KEYS = {
    "accession_number",
    "counts",
    "payload_bytes",
    "result",
    "schema_version",
    "status",
}


def encode_arelle_result(
    result: ArelleFilingResult,
    *,
    max_bytes: int,
) -> bytes:
    """Encode one result and enforce the configured transport bound."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    envelope: dict[str, Any] = {
        "accession_number": result.accession_number,
        "counts": asdict(result.counts),
        "payload_bytes": 0,
        "result": asdict(result),
        "schema_version": ARELLE_RESULT_SCHEMA_VERSION,
        "status": result.status,
    }
    payload = b""
    for _ in range(8):
        payload = _json_bytes(envelope)
        if envelope["payload_bytes"] == len(payload):
            break
        envelope["payload_bytes"] = len(payload)
    else:  # pragma: no cover - byte-count digit width converges immediately
        raise InlineXbrlExtractionError("Arelle result payload size did not stabilize")
    if len(payload) > max_bytes:
        raise InlineXbrlExtractionError(
            f"Arelle result payload exceeded {max_bytes} bytes: {len(payload)}"
        )
    return payload


def decode_arelle_result(
    payload: bytes,
    *,
    max_bytes: int,
    expected_accession_number: str | None = None,
) -> ArelleFilingResult:
    """Decode and strictly validate one bounded Arelle result envelope."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if len(payload) > max_bytes:
        raise InlineXbrlExtractionError(
            f"Arelle result payload exceeded {max_bytes} bytes: {len(payload)}"
        )
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InlineXbrlExtractionError("Arelle result payload was not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_KEYS:
        raise InlineXbrlExtractionError("Arelle result envelope shape was invalid")
    if envelope["schema_version"] != ARELLE_RESULT_SCHEMA_VERSION:
        raise InlineXbrlExtractionError(
            f"Unsupported Arelle result schema: {envelope['schema_version']}"
        )
    if envelope["payload_bytes"] != len(payload):
        raise InlineXbrlExtractionError("Arelle result payload byte count did not match")
    accession_number = _required_string(envelope, "accession_number")
    if expected_accession_number is not None and accession_number != expected_accession_number:
        raise InlineXbrlExtractionError(
            "Arelle result accession did not match the worker request"
        )
    result_value = envelope["result"]
    if not isinstance(result_value, dict):
        raise InlineXbrlExtractionError("Arelle result body was not an object")
    result = _result_from_dict(result_value)
    if result.accession_number != accession_number or result.status != envelope["status"]:
        raise InlineXbrlExtractionError("Arelle result envelope identity did not match its body")
    expected_counts = _counts_from_dict(envelope["counts"])
    if result.counts != expected_counts:
        raise InlineXbrlExtractionError("Arelle result record counts did not match")
    return result


def arelle_result_sha256(payload: bytes) -> str:
    """Return the content hash used by future exact-result caching."""
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _result_from_dict(value: dict[str, Any]) -> ArelleFilingResult:
    try:
        return ArelleFilingResult(
            accession_number=str(value["accession_number"]),
            status=value["status"],
            cik=_optional_string(value.get("cik")),
            form=_optional_string(value.get("form")),
            filing_date=_optional_string(value.get("filing_date")),
            fiscal_year=value.get("fiscal_year"),
            fiscal_period=_optional_string(value.get("fiscal_period")),
            facts=tuple(_fact_from_dict(item) for item in value.get("facts", [])),
            concepts=tuple(_concept_from_dict(item) for item in value.get("concepts", [])),
            relationships=tuple(
                _relationship_from_dict(item) for item in value.get("relationships", [])
            ),
            diagnostics=tuple(
                _diagnostic_from_dict(item) for item in value.get("diagnostics", [])
            ),
            namespaces=tuple(str(item) for item in value.get("namespaces", [])),
            timings=ArelleTimings(**value.get("timings", {})),
            cache_state=str(value.get("cache_state", "unknown")),
            arelle_version=_optional_string(value.get("arelle_version")),
            result_schema_version=str(value["result_schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InlineXbrlExtractionError("Arelle result body was invalid") from exc


def _fact_from_dict(value: dict[str, Any]) -> ExtractedFact:
    return ExtractedFact(
        concept_key=_qname_from_dict(value["concept_key"]),
        context_key=_context_from_dict(value["context_key"]),
        value=_optional_string(value.get("value")),
        value_raw=_optional_string(value.get("value_raw")),
        nil=bool(value["nil"]),
        unit_key=(
            _unit_from_dict(value["unit_key"])
            if value.get("unit_key") is not None
            else None
        ),
        decimals=_optional_string(value.get("decimals")),
        precision=_optional_string(value.get("precision")),
        source_document=_optional_string(value.get("source_document")),
        source_line=value.get("source_line"),
    )


def _concept_from_dict(value: dict[str, Any]) -> ConceptEvidence:
    return ConceptEvidence(
        concept_key=_qname_from_dict(value["concept_key"]),
        standard_label=_optional_string(value.get("standard_label")),
        documentation=_optional_string(value.get("documentation")),
        type_key=(
            _qname_from_dict(value["type_key"])
            if value.get("type_key") is not None
            else None
        ),
        is_numeric=bool(value["is_numeric"]),
        numeric_kind=_optional_string(value.get("numeric_kind")),
        period_type=_optional_string(value.get("period_type")),
        balance=_optional_string(value.get("balance")),
        references=tuple(str(item) for item in value.get("references", [])),
    )


def _relationship_from_dict(value: dict[str, Any]) -> RelationshipEdge:
    return RelationshipEdge(
        network_kind=value["network_kind"],
        link_role=str(value["link_role"]),
        from_concept=_qname_from_dict(value["from_concept"]),
        to_concept=_qname_from_dict(value["to_concept"]),
        order=_optional_string(value.get("order")),
        weight=_optional_string(value.get("weight")),
        preferred_label=_optional_string(value.get("preferred_label")),
    )


def _diagnostic_from_dict(value: dict[str, Any]) -> DiagnosticRecord:
    return DiagnosticRecord(
        category=str(value["category"]),
        severity=value["severity"],
        code=str(value["code"]),
        message=str(value["message"]),
        concept_key=(
            _qname_from_dict(value["concept_key"])
            if value.get("concept_key") is not None
            else None
        ),
        context_id=_optional_string(value.get("context_id")),
        source_document=_optional_string(value.get("source_document")),
    )


def _context_from_dict(value: dict[str, Any]) -> ContextKey:
    return ContextKey(
        context_id=_optional_string(value.get("context_id")),
        entity_scheme=str(value["entity_scheme"]),
        entity_identifier=str(value["entity_identifier"]),
        period_type=value["period_type"],
        start_date=_optional_string(value.get("start_date")),
        end_date=_optional_string(value.get("end_date")),
        instant_date=_optional_string(value.get("instant_date")),
        dimensions=tuple(
            DimensionValue(
                dimension=_qname_from_dict(item["dimension"]),
                member=(
                    _qname_from_dict(item["member"])
                    if item.get("member") is not None
                    else None
                ),
                typed_member_xml=_optional_string(item.get("typed_member_xml")),
            )
            for item in value.get("dimensions", [])
        ),
    )


def _unit_from_dict(value: dict[str, Any]) -> UnitKey:
    return UnitKey(
        numerator=tuple(_qname_from_dict(item) for item in value["numerator"]),
        denominator=tuple(_qname_from_dict(item) for item in value.get("denominator", [])),
    )


def _qname_from_dict(value: dict[str, Any]) -> QNameKey:
    return QNameKey(
        namespace_uri=str(value["namespace_uri"]),
        local_name=str(value["local_name"]),
        prefix=_optional_string(value.get("prefix")),
    )


def _counts_from_dict(value: Any) -> ArelleRecordCounts:
    if not isinstance(value, dict):
        raise InlineXbrlExtractionError("Arelle result counts were invalid")
    try:
        return ArelleRecordCounts(
            facts=int(value["facts"]),
            concepts=int(value["concepts"]),
            relationships=int(value["relationships"]),
            diagnostics=int(value["diagnostics"]),
            namespaces=int(value["namespaces"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InlineXbrlExtractionError("Arelle result counts were invalid") from exc


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise InlineXbrlExtractionError(f"Arelle result {key} was invalid")
    return item


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
