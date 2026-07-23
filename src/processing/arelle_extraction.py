"""Extract project-owned evidence records from one live Arelle model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from arelle import ModelDocument, XbrlConst
from arelle.ModelDtsObject import ModelConcept

from src.processing.arelle_evidence import (
    ArelleConceptRecord,
    ArelleContextRecord,
    ArelleDiagnosticRecord,
    ArelleDimensionRecord,
    ArelleFactRecord,
    ArelleFormulaAssertionRecord,
    ArelleNamespaceRecord,
    ArelleRecordCounts,
    ArelleRelationshipRecord,
    ArelleSourceDocumentRecord,
    ArelleUnitRecord,
)


@dataclass(frozen=True)
class ExtractedArelleEvidence:
    """Serializable evidence collected before the live model is closed."""

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


def extract_arelle_evidence(
    model_xbrl: Any,
    log_messages: list[dict[str, Any]],
) -> ExtractedArelleEvidence:
    """Extract all required evidence without retaining live Arelle objects."""
    object_references: dict[str, tuple[str, str]] = {}
    facts = _extract_facts(model_xbrl, object_references)
    concepts = _extract_concepts(model_xbrl, object_references)
    contexts = _extract_contexts(model_xbrl)
    units = _extract_units(model_xbrl)
    relationships = _extract_relationships(model_xbrl, object_references)
    formula_assertions = _extract_formula_assertions(model_xbrl)
    diagnostics = _extract_diagnostics(log_messages, object_references)
    namespaces = _extract_namespaces(model_xbrl)
    source_documents = _extract_source_documents(model_xbrl)
    return ExtractedArelleEvidence(
        facts=facts,
        concepts=concepts,
        contexts=contexts,
        units=units,
        relationships=relationships,
        formula_assertions=formula_assertions,
        diagnostics=diagnostics,
        namespaces=namespaces,
        source_documents=source_documents,
        record_counts=ArelleRecordCounts(
            facts=len(facts),
            concepts=len(concepts),
            contexts=len(contexts),
            units=len(units),
            relationships=len(relationships),
            formula_assertions=len(formula_assertions),
            diagnostics=len(diagnostics),
            source_documents=len(source_documents),
        ),
    )


def _extract_facts(
    model_xbrl: Any,
    object_references: dict[str, tuple[str, str]],
) -> tuple[ArelleFactRecord, ...]:
    records: list[ArelleFactRecord] = []
    for index, fact in enumerate(model_xbrl.factsInInstance):
        qname = _qname_text(getattr(fact, "qname", None))
        context_id = _optional_text(getattr(fact, "contextID", None))
        unit_id = _optional_text(getattr(fact, "unitID", None))
        raw_value = getattr(fact, "value", None)
        display_value = (
            None
            if bool(getattr(fact, "isNil", False)) or raw_value is None
            else str(raw_value)
        )
        concept = getattr(fact, "concept", None)
        numeric_value = None
        if concept is not None and bool(getattr(concept, "isNumeric", False)) and display_value is not None:
            numeric_value = _optional_text(getattr(fact, "xValue", None))
        evidence_id = _evidence_id(
            "fact",
            str(index),
            qname,
            context_id or "",
            unit_id or "",
            display_value or "",
        )
        records.append(
            ArelleFactRecord(
                evidence_id=evidence_id,
                concept_id=_concept_id(getattr(fact, "qname", None)),
                context_id=context_id,
                unit_id=unit_id,
                display_value=display_value,
                numeric_value=numeric_value,
                is_nil=bool(getattr(fact, "isNil", False)),
                decimals=_optional_text(getattr(fact, "decimals", None)),
                precision=_optional_text(getattr(fact, "precision", None)),
                xml_lang=_optional_text(getattr(fact, "xmlLang", None)),
            )
        )
        _register_object_reference(fact, "fact", evidence_id, object_references)
    return tuple(records)


def _extract_concepts(
    model_xbrl: Any,
    object_references: dict[str, tuple[str, str]],
) -> tuple[ArelleConceptRecord, ...]:
    records: list[ArelleConceptRecord] = []
    concepts = sorted(
        model_xbrl.qnameConcepts.values(),
        key=lambda concept: _qname_text(getattr(concept, "qname", None)),
    )
    label_set = model_xbrl.relationshipSet(XbrlConst.conceptLabel)
    reference_set = model_xbrl.relationshipSet(XbrlConst.conceptReference)
    for concept in concepts:
        qname = getattr(concept, "qname", None)
        evidence_id = _concept_id(qname)
        references = tuple(
            sorted(
                {
                    text
                    for relationship in reference_set.fromModelObject(concept)
                    if (text := _resource_text(relationship.toModelObject))
                }
            )
        )
        records.append(
            ArelleConceptRecord(
                evidence_id=evidence_id,
                qname=_qname_text(qname),
                namespace_uri=str(getattr(qname, "namespaceURI", "") or ""),
                local_name=str(getattr(qname, "localName", "") or ""),
                prefix=_optional_text(getattr(qname, "prefix", None)),
                label=_concept_label_for_role(
                    label_set,
                    concept,
                    XbrlConst.standardLabel,
                )
                or _optional_text(concept.label(lang="en", strip=True)),
                documentation=_concept_label_for_role(
                    label_set,
                    concept,
                    XbrlConst.documentationLabel,
                ),
                type_qname=_optional_qname_text(getattr(concept, "typeQname", None)),
                base_type=_optional_text(getattr(concept, "baseXbrliType", None)),
                period_type=_optional_text(getattr(concept, "periodType", None)),
                balance=_optional_text(getattr(concept, "balance", None)),
                is_numeric=bool(getattr(concept, "isNumeric", False)),
                is_abstract=bool(getattr(concept, "isAbstract", False)),
                references=references,
            )
        )
        _register_object_reference(concept, "concept", evidence_id, object_references)
    return tuple(records)


def _extract_contexts(model_xbrl: Any) -> tuple[ArelleContextRecord, ...]:
    records: list[ArelleContextRecord] = []
    for context_id, context in sorted(model_xbrl.contexts.items()):
        entity_identifier = getattr(context, "entityIdentifier", None)
        entity_scheme = None
        entity_value = None
        if isinstance(entity_identifier, tuple) and len(entity_identifier) == 2:
            entity_scheme = _optional_text(entity_identifier[0])
            entity_value = _optional_text(entity_identifier[1])
        dimensions = tuple(
            sorted(
                (
                    ArelleDimensionRecord(
                        dimension=_qname_text(dimension_qname),
                        member=_dimension_member_text(dimension_value),
                        is_typed=not bool(getattr(dimension_value, "isExplicit", False)),
                    )
                    for dimension_qname, dimension_value in context.qnameDims.items()
                ),
                key=lambda record: (record.dimension, record.member),
            )
        )
        period_type = "forever"
        start_date = None
        end_date = None
        instant_date = None
        if bool(getattr(context, "isInstantPeriod", False)):
            period_type = "instant"
            instant_date = _date_text(getattr(context, "instantDate", None))
        elif bool(getattr(context, "isStartEndPeriod", False)):
            period_type = "duration"
            start_date = _date_text(getattr(context, "startDatetime", None))
            end_date = _date_text(getattr(context, "endDate", None))
        records.append(
            ArelleContextRecord(
                context_id=str(context_id),
                entity_scheme=entity_scheme,
                entity_identifier=entity_value,
                period_type=period_type,
                start_date=start_date,
                end_date=end_date,
                instant_date=instant_date,
                dimensions=dimensions,
            )
        )
    return tuple(records)


def _extract_units(model_xbrl: Any) -> tuple[ArelleUnitRecord, ...]:
    records: list[ArelleUnitRecord] = []
    for unit_id, unit in sorted(model_xbrl.units.items()):
        numerator, denominator = unit.measures
        records.append(
            ArelleUnitRecord(
                unit_id=str(unit_id),
                numerator_measures=tuple(_qname_text(measure) for measure in numerator),
                denominator_measures=tuple(_qname_text(measure) for measure in denominator),
            )
        )
    return tuple(records)


def _extract_relationships(
    model_xbrl: Any,
    object_references: dict[str, tuple[str, str]],
) -> tuple[ArelleRelationshipRecord, ...]:
    records: list[ArelleRelationshipRecord] = []
    evidence_ids_by_signature: dict[tuple[str, ...], str] = {}
    base_set_keys = sorted(
        model_xbrl.baseSets,
        key=lambda key: tuple(str(value or "") for value in key),
    )
    for arcrole, link_role, link_qname, arc_qname in base_set_keys:
        if not link_role or link_qname is None or arc_qname is None:
            continue
        relationship_set = model_xbrl.relationshipSet(
            arcrole,
            link_role,
            link_qname,
            arc_qname,
        )
        for relationship in relationship_set.modelRelationships:
            from_id = _endpoint_id(relationship.fromModelObject)
            to_id = _endpoint_id(relationship.toModelObject)
            order = _optional_text(getattr(relationship, "order", None))
            weight = _optional_text(getattr(relationship, "weight", None))
            preferred_label = _optional_text(getattr(relationship, "preferredLabel", None))
            target_role = _optional_text(getattr(relationship, "targetRole", None))
            signature = (
                str(arcrole),
                str(link_role),
                from_id,
                to_id,
                order or "",
                weight or "",
                preferred_label or "",
                target_role or "",
            )
            existing_evidence_id = evidence_ids_by_signature.get(signature)
            if existing_evidence_id is not None:
                _register_object_reference(
                    relationship,
                    "relationship",
                    existing_evidence_id,
                    object_references,
                )
                continue
            evidence_id = _evidence_id("relationship", *signature)
            evidence_ids_by_signature[signature] = evidence_id
            records.append(
                ArelleRelationshipRecord(
                    evidence_id=evidence_id,
                    network_kind=_network_kind(str(arcrole)),
                    arcrole=str(arcrole),
                    link_role=str(link_role),
                    from_id=from_id,
                    to_id=to_id,
                    order=order,
                    weight=weight,
                    preferred_label=preferred_label,
                    target_role=target_role,
                )
            )
            _register_object_reference(
                relationship,
                "relationship",
                evidence_id,
                object_references,
            )
    return tuple(records)


def _extract_formula_assertions(model_xbrl: Any) -> tuple[ArelleFormulaAssertionRecord, ...]:
    assertions: dict[str, ArelleFormulaAssertionRecord] = {}
    model_assertions = set(getattr(model_xbrl, "modelVariableSets", ())) | set(
        getattr(model_xbrl, "modelConsistencyAssertions", ())
    )
    for assertion in model_assertions:
        if not hasattr(assertion, "countSatisfied"):
            continue
        assertion_id = _optional_text(getattr(assertion, "id", None)) or _endpoint_id(assertion)
        assertions[assertion_id] = ArelleFormulaAssertionRecord(
            assertion_id=assertion_id,
            assertion_type=assertion.__class__.__name__,
            satisfied_count=int(getattr(assertion, "countSatisfied", 0)),
            unsatisfied_count=int(getattr(assertion, "countNotSatisfied", 0)),
            ok_message_count=int(getattr(assertion, "countOkMessages", 0)),
            warning_message_count=int(getattr(assertion, "countWarningMessages", 0)),
            error_message_count=int(getattr(assertion, "countErrorMessages", 0)),
        )
    for error in getattr(model_xbrl, "errors", ()):
        if not isinstance(error, dict):
            continue
        for assertion_id, counts in error.items():
            if not isinstance(counts, tuple) or len(counts) != 5:
                continue
            assertions[str(assertion_id)] = ArelleFormulaAssertionRecord(
                assertion_id=str(assertion_id),
                assertion_type="formula_assertion",
                satisfied_count=int(counts[0]),
                unsatisfied_count=int(counts[1]),
                ok_message_count=int(counts[2]),
                warning_message_count=int(counts[3]),
                error_message_count=int(counts[4]),
            )
    return tuple(assertions[key] for key in sorted(assertions))


def _extract_diagnostics(
    log_messages: list[dict[str, Any]],
    object_references: dict[str, tuple[str, str]],
) -> tuple[ArelleDiagnosticRecord, ...]:
    records: list[ArelleDiagnosticRecord] = []
    for message in log_messages:
        fact_ids: set[str] = set()
        relationship_ids: set[str] = set()
        source_references: set[str] = set()
        refs = message.get("refs")
        if isinstance(refs, list):
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                object_id = _optional_text(ref.get("objectId"))
                if object_id and object_id in object_references:
                    reference_kind, evidence_id = object_references[object_id]
                    if reference_kind == "fact":
                        fact_ids.add(evidence_id)
                    elif reference_kind == "relationship":
                        relationship_ids.add(evidence_id)
                source_reference = _diagnostic_source_reference(ref)
                if source_reference:
                    source_references.add(source_reference)
        records.append(
            ArelleDiagnosticRecord(
                severity=str(message.get("levelname") or "unknown").lower(),
                code=str(message.get("messageCode") or "arelle:unknown"),
                message=str(message.get("msg") or ""),
                fact_ids=tuple(sorted(fact_ids)),
                relationship_ids=tuple(sorted(relationship_ids)),
                source_references=tuple(sorted(source_references)),
            )
        )
    return tuple(records)


def _extract_namespaces(model_xbrl: Any) -> tuple[ArelleNamespaceRecord, ...]:
    namespaces: set[tuple[str | None, str]] = set()
    for document in model_xbrl.urlDocs.values():
        root = getattr(document, "xmlRootElement", None)
        nsmap = getattr(root, "nsmap", {}) if root is not None else {}
        if isinstance(nsmap, dict):
            for prefix, namespace_uri in nsmap.items():
                if namespace_uri:
                    namespaces.add((_optional_text(prefix), str(namespace_uri)))
    return tuple(
        ArelleNamespaceRecord(prefix=prefix, namespace_uri=namespace_uri)
        for prefix, namespace_uri in sorted(namespaces, key=lambda item: (item[0] or "", item[1]))
    )


def _extract_source_documents(model_xbrl: Any) -> tuple[ArelleSourceDocumentRecord, ...]:
    records: list[ArelleSourceDocumentRecord] = []
    for uri, document in sorted(model_xbrl.urlDocs.items(), key=lambda item: str(item[0])):
        path = Path(str(uri))
        content_sha256 = file_sha256(path) if path.is_file() else None
        document_type = getattr(document, "type", "unknown")
        type_name = _document_type_name(document_type)
        records.append(
            ArelleSourceDocumentRecord(
                uri=str(uri),
                document_type=str(type_name),
                target_namespace=_optional_text(getattr(document, "targetNamespace", None)),
                content_sha256=content_sha256,
            )
        )
    return tuple(records)


def _network_kind(arcrole: str) -> str:
    if arcrole == XbrlConst.parentChild:
        return "presentation"
    if arcrole in {XbrlConst.summationItem, getattr(XbrlConst, "summationItem11", "")}:
        return "calculation"
    if arcrole == XbrlConst.conceptLabel:
        return "label"
    if arcrole == XbrlConst.conceptReference:
        return "reference"
    if XbrlConst.isFormulaArcrole(arcrole):
        return "formula"
    if "xbrl.org/int/dim/arcrole" in arcrole or arcrole in {
        XbrlConst.generalSpecial,
        XbrlConst.essenceAlias,
        XbrlConst.requiresElement,
        XbrlConst.similarTuples,
    }:
        return "definition"
    return "other"


def _endpoint_id(model_object: Any) -> str:
    qname = getattr(model_object, "qname", None)
    if isinstance(model_object, ModelConcept):
        return _concept_id(qname)
    model_document = getattr(model_object, "modelDocument", None)
    document_uri = _optional_text(getattr(model_document, "uri", None)) or ""
    role = _optional_text(getattr(model_object, "role", None)) or ""
    identifier = _optional_text(getattr(model_object, "id", None)) or ""
    xlink_label = _optional_text(getattr(model_object, "xlinkLabel", None)) or ""
    xml_lang = _optional_text(getattr(model_object, "xmlLang", None)) or ""
    source_line = _optional_text(getattr(model_object, "sourceline", None)) or ""
    text = _resource_text(model_object) or ""
    return _evidence_id(
        model_object.__class__.__name__.lower(),
        _qname_text(qname),
        document_uri,
        source_line,
        role,
        identifier,
        xlink_label,
        xml_lang,
        text,
    )


def _concept_id(qname: Any) -> str:
    return f"concept:{_qname_text(qname)}"


def _qname_text(qname: Any) -> str:
    if qname is None:
        return "{}"
    namespace_uri = str(getattr(qname, "namespaceURI", "") or "")
    local_name = str(getattr(qname, "localName", "") or qname)
    return f"{{{namespace_uri}}}{local_name}"


def _optional_qname_text(qname: Any) -> str | None:
    return _qname_text(qname) if qname is not None else None


def _resource_text(resource: Any) -> str | None:
    for attribute in ("textValue", "stringValue", "viewText"):
        value = getattr(resource, attribute, None)
        if callable(value):
            value = value()
        text = _optional_text(value)
        if text:
            return text
    return None


def _concept_label_for_role(
    label_set: Any,
    concept: Any,
    role: str,
) -> str | None:
    for relationship in label_set.fromModelObject(concept):
        resource = relationship.toModelObject
        if getattr(resource, "role", None) == role:
            text = _resource_text(resource)
            if text:
                return text
    return None


def _dimension_member_text(dimension_value: Any) -> str:
    if bool(getattr(dimension_value, "isExplicit", False)):
        return _qname_text(getattr(dimension_value, "memberQname", None))
    typed_member = getattr(dimension_value, "typedMember", None)
    return str(
        getattr(typed_member, "xValue", None)
        or getattr(typed_member, "stringValue", None)
        or ""
    )


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    date_value = value.date() if isinstance(value, datetime) else value
    return str(date_value.isoformat()) if hasattr(date_value, "isoformat") else str(date_value)


def _document_type_name(value: Any) -> str:
    try:
        return str(ModelDocument.Type.typeName[int(value)])
    except (IndexError, TypeError, ValueError):
        return str(value)


def _diagnostic_source_reference(ref: dict[str, Any]) -> str | None:
    href = _optional_text(ref.get("href"))
    source_line = ref.get("sourceLine")
    if href and source_line is not None:
        return f"{href}:line:{source_line}"
    return href


def _register_object_reference(
    model_object: Any,
    kind: str,
    evidence_id: str,
    object_references: dict[str, tuple[str, str]],
) -> None:
    object_id = getattr(model_object, "objectId", None)
    if callable(object_id):
        value = _optional_text(object_id())
        if value:
            object_references[value] = (kind, evidence_id)


def _evidence_id(kind: str, *parts: str) -> str:
    digest = sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def file_sha256(path: Path) -> str:
    """Return a stable SHA-256 for a local source document."""
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
