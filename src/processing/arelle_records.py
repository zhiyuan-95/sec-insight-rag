"""Project-owned records for the Plan 203 Arelle boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ARELLE_RESULT_SCHEMA_VERSION = "arelle-result-v1"

ArelleResultStatus = Literal["complete", "degraded", "failed"]
DiagnosticSeverity = Literal["info", "warning", "error", "fatal"]
NetworkKind = Literal["presentation", "calculation", "definition"]


@dataclass(frozen=True)
class ArelleResourceLimits:
    """Safety ceilings for one canonical accession load."""

    max_package_bytes: int = 1 * 1024 * 1024 * 1024
    max_package_files: int = 10_000
    load_timeout_seconds: float = 120.0
    validation_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 180.0
    max_facts: int = 500_000
    max_concepts: int = 250_000
    max_relationships: int = 2_000_000
    max_diagnostics: int = 100_000
    max_serialized_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True, order=True)
class QNameKey:
    """Stable QName identity with an optional filing display prefix."""

    namespace_uri: str
    local_name: str
    prefix: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.local_name.strip():
            raise ValueError("QName local_name cannot be blank")


@dataclass(frozen=True, order=True)
class DimensionValue:
    """Canonical explicit or typed dimension value."""

    dimension: QNameKey
    member: QNameKey | None = None
    typed_member_xml: str | None = None

    def __post_init__(self) -> None:
        if (self.member is None) == (self.typed_member_xml is None):
            raise ValueError(
                "DimensionValue requires exactly one of member or typed_member_xml"
            )


@dataclass(frozen=True)
class ContextKey:
    """Serializable XBRL context identity."""

    context_id: str | None
    entity_scheme: str
    entity_identifier: str
    period_type: Literal["instant", "duration", "forever", "unknown"]
    start_date: str | None = None
    end_date: str | None = None
    instant_date: str | None = None
    dimensions: tuple[DimensionValue, ...] = ()


@dataclass(frozen=True)
class UnitKey:
    """Ordered numerator and denominator measures for an XBRL unit."""

    numerator: tuple[QNameKey, ...]
    denominator: tuple[QNameKey, ...] = ()


@dataclass(frozen=True)
class ExtractedFact:
    """One reported fact detached from live Arelle objects."""

    concept_key: QNameKey
    context_key: ContextKey
    value: str | None
    value_raw: str | None
    nil: bool
    unit_key: UnitKey | None = None
    decimals: str | None = None
    precision: str | None = None
    source_document: str | None = None
    source_line: int | None = None


@dataclass(frozen=True)
class ConceptEvidence:
    """Taxonomy metadata used by deterministic mapping inference."""

    concept_key: QNameKey
    standard_label: str | None
    documentation: str | None
    type_key: QNameKey | None
    is_numeric: bool
    numeric_kind: str | None
    period_type: str | None
    balance: str | None
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationshipEdge:
    """Filing-relevant taxonomy relationship detached from Arelle."""

    network_kind: NetworkKind
    link_role: str
    from_concept: QNameKey
    to_concept: QNameKey
    order: str | None = None
    weight: str | None = None
    preferred_label: str | None = None


@dataclass(frozen=True)
class DiagnosticRecord:
    """Structured load, validation, or extraction diagnostic."""

    category: str
    severity: DiagnosticSeverity
    code: str
    message: str
    concept_key: QNameKey | None = None
    context_id: str | None = None
    source_document: str | None = None


@dataclass(frozen=True)
class ArelleTimings:
    """Measured durations for one accession."""

    load_seconds: float = 0.0
    validation_seconds: float = 0.0
    extraction_seconds: float = 0.0
    total_seconds: float = 0.0


@dataclass(frozen=True)
class ArelleFilingRequest:
    """Canonical request for one verified local filing package."""

    entry_document: str
    package_manifest: str
    cik: str
    accession_number: str
    form: str
    filing_date: str
    fiscal_year: int | None
    fiscal_period: str | None
    sec_user_agent: str
    cache_directory: str
    taxonomy_package_paths: tuple[str, ...] = ()
    validation_profile: str = "xbrl-core"
    resource_policy_version: str = "arelle-resource-policy-v1"
    limits: ArelleResourceLimits = ArelleResourceLimits()

    def __post_init__(self) -> None:
        required = {
            "entry_document": self.entry_document,
            "package_manifest": self.package_manifest,
            "cik": self.cik,
            "accession_number": self.accession_number,
            "form": self.form,
            "filing_date": self.filing_date,
            "sec_user_agent": self.sec_user_agent,
            "cache_directory": self.cache_directory,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} cannot be blank")


@dataclass(frozen=True)
class ArelleRecordCounts:
    """Envelope counts used to reject truncated or inconsistent payloads."""

    facts: int
    concepts: int
    relationships: int
    diagnostics: int
    namespaces: int


@dataclass(frozen=True)
class ArelleFilingResult:
    """Complete project-owned result for one accession."""

    accession_number: str
    status: ArelleResultStatus
    cik: str | None = None
    form: str | None = None
    filing_date: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    facts: tuple[ExtractedFact, ...] = ()
    concepts: tuple[ConceptEvidence, ...] = ()
    relationships: tuple[RelationshipEdge, ...] = ()
    diagnostics: tuple[DiagnosticRecord, ...] = ()
    namespaces: tuple[str, ...] = ()
    timings: ArelleTimings = ArelleTimings()
    cache_state: str = "unknown"
    arelle_version: str | None = None
    result_schema_version: str = ARELLE_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.accession_number.strip():
            raise ValueError("accession_number cannot be blank")
        if self.status not in {"complete", "degraded", "failed"}:
            raise ValueError(f"Unknown Arelle result status: {self.status}")
        if self.result_schema_version != ARELLE_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported Arelle result schema: {self.result_schema_version}"
            )
        if self.status == "failed" and (self.facts or self.concepts or self.relationships):
            raise ValueError("Failed Arelle results cannot contain trusted records")

    @property
    def counts(self) -> ArelleRecordCounts:
        """Return counts embedded in the worker transport envelope."""
        return ArelleRecordCounts(
            facts=len(self.facts),
            concepts=len(self.concepts),
            relationships=len(self.relationships),
            diagnostics=len(self.diagnostics),
            namespaces=len(self.namespaces),
        )


def failed_arelle_result(
    accession_number: str,
    *,
    code: str,
    message: str,
    category: str = "worker",
) -> ArelleFilingResult:
    """Build a small failed envelope with no partially trusted records."""
    return ArelleFilingResult(
        accession_number=accession_number,
        status="failed",
        diagnostics=(
            DiagnosticRecord(
                category=category,
                severity="fatal",
                code=code,
                message=message,
            ),
        ),
    )
