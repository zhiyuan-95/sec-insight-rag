from __future__ import annotations

from dataclasses import replace

import pytest

from src.processing.arelle_codec import (
    arelle_result_sha256,
    decode_arelle_result,
    encode_arelle_result,
)
from src.processing.arelle_records import (
    ArelleFilingResult,
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
from src.processing.errors import InlineXbrlExtractionError


def _complete_result() -> ArelleFilingResult:
    concept_key = QNameKey(
        namespace_uri="https://example.com/msft/2025",
        local_name="OperatingIncome",
        prefix="msft",
    )
    dimension = DimensionValue(
        dimension=QNameKey(
            namespace_uri="http://fasb.org/us-gaap/2025",
            local_name="StatementBusinessSegmentsAxis",
            prefix="us-gaap",
        ),
        member=QNameKey(
            namespace_uri="https://example.com/msft/2025",
            local_name="CloudMember",
            prefix="msft",
        ),
    )
    context = ContextKey(
        context_id="D2025",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier="0000789019",
        period_type="duration",
        start_date="2024-07-01",
        end_date="2025-06-30",
        dimensions=(dimension,),
    )
    unit = UnitKey(
        numerator=(
            QNameKey(
                namespace_uri="http://www.xbrl.org/2003/iso4217",
                local_name="USD",
                prefix="iso4217",
            ),
        )
    )
    return ArelleFilingResult(
        accession_number="0000789019-25-100235",
        status="complete",
        facts=(
            ExtractedFact(
                concept_key=concept_key,
                context_key=context,
                value="128528000000",
                value_raw="128,528",
                nil=False,
                unit_key=unit,
                decimals="-6",
                source_document="filing/msft-20250630.htm",
                source_line=42,
            ),
        ),
        concepts=(
            ConceptEvidence(
                concept_key=concept_key,
                standard_label="Operating income",
                documentation="Income from operations.",
                type_key=QNameKey(
                    namespace_uri="http://www.xbrl.org/dtr/type/numeric",
                    local_name="monetaryItemType",
                ),
                is_numeric=True,
                numeric_kind="monetary",
                period_type="duration",
                balance="credit",
            ),
        ),
        relationships=(
            RelationshipEdge(
                network_kind="presentation",
                link_role="http://example.com/role/income-statement",
                from_concept=QNameKey(
                    namespace_uri="http://fasb.org/us-gaap/2025",
                    local_name="OperatingIncomeLoss",
                    prefix="us-gaap",
                ),
                to_concept=concept_key,
                order="10",
            ),
        ),
        diagnostics=(
            DiagnosticRecord(
                category="validation",
                severity="warning",
                code="example:warning",
                message="Example diagnostic",
            ),
        ),
        namespaces=(
            "http://fasb.org/us-gaap/2025",
            "https://example.com/msft/2025",
        ),
        cache_state="cold",
        arelle_version="2.41.5",
    )


def test_arelle_result_codec_round_trips_complete_result() -> None:
    result = _complete_result()

    payload = encode_arelle_result(result, max_bytes=100_000)
    decoded = decode_arelle_result(
        payload,
        max_bytes=100_000,
        expected_accession_number=result.accession_number,
    )

    assert decoded == result
    assert len(payload) > 0
    assert len(arelle_result_sha256(payload)) == 64


def test_qname_identity_ignores_display_prefix() -> None:
    assert QNameKey(
        namespace_uri="http://fasb.org/us-gaap/2025",
        local_name="Revenue",
        prefix="us-gaap",
    ) == QNameKey(
        namespace_uri="http://fasb.org/us-gaap/2025",
        local_name="Revenue",
        prefix="different-display-prefix",
    )


def test_arelle_result_codec_rejects_wrong_accession() -> None:
    payload = encode_arelle_result(_complete_result(), max_bytes=100_000)

    with pytest.raises(InlineXbrlExtractionError, match="accession"):
        decode_arelle_result(
            payload,
            max_bytes=100_000,
            expected_accession_number="other-accession",
        )


def test_arelle_result_codec_rejects_oversized_payload() -> None:
    with pytest.raises(InlineXbrlExtractionError, match="exceeded"):
        encode_arelle_result(_complete_result(), max_bytes=10)


def test_arelle_result_codec_rejects_invalid_json() -> None:
    with pytest.raises(InlineXbrlExtractionError, match="valid JSON"):
        decode_arelle_result(b"not-json", max_bytes=100)


def test_failed_arelle_result_contains_no_trusted_records() -> None:
    result = failed_arelle_result(
        "0000789019-25-100235",
        code="worker_timeout",
        message="Worker exceeded its deadline",
    )

    assert result.status == "failed"
    assert result.facts == ()
    assert result.diagnostics[0].severity == "fatal"

    with pytest.raises(ValueError, match="cannot contain trusted records"):
        replace(result, facts=_complete_result().facts)
