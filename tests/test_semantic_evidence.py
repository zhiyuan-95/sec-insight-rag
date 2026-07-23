from datetime import date
from decimal import Decimal

import pytest

from src.processing import (
    ARELLE_RESULT_COMPLETE,
    ArelleConceptRecord,
    ArelleDiagnosticRecord,
    ArelleFactRecord,
    ArelleFilingIdentity,
    ArelleFilingResult,
    ArelleFormulaAssertionRecord,
    ArelleRecordCounts,
    ArelleRelationshipRecord,
    ArelleTimingRecord,
    CompanyPrecedenceResult,
    ConceptIdentity,
    ConceptMetadataResolution,
    FactPrecedenceResolution,
    PrecedenceMetadataField,
    PrecedenceSelectedObservation,
    PrecedenceStatementNetwork,
    ReconciledObservation,
    ReconciliationSourceObservation,
    SemanticEvidencePeriod,
    SemanticEvidencePacket,
    SemanticFactIdentity,
    StatementNetworkIdentity,
    build_semantic_evidence_packet,
    canonical_metric_targets,
    group_semantic_evidence_packets,
)
from src.processing.inline_xbrl import INLINE_XBRL_SOURCE
from src.processing.observation_reconciliation import RECONCILIATION_ARELLE_ONLY
from src.processing.xbrl_normalizer import NormalizedFact


def test_packet_contains_target_and_arelle_semantic_evidence() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id="fact-revenue",
    )
    relationship = ArelleRelationshipRecord(
        evidence_id="relationship-revenue-detail",
        network_kind="calculation",
        arcrole="summation-item",
        link_role="income-statement",
        from_id="concept-target-revenue",
        to_id="concept-detail",
        order="1",
        weight="1",
        preferred_label=None,
        target_role=None,
    )
    precedence = _precedence_result(
        selected,
        metadata=(
            _metadata(
                concept="CustomerRevenue",
                label="Customer revenue",
                description="Revenue from customer contracts",
            ),
            _metadata(
                concept="RevenueDetail",
                label="Revenue detail",
                description="Context for the reported revenue concept",
            ),
            _metadata(
                concept="UnrelatedDisclosure",
                label="Unrelated disclosure",
                description="A taxonomy concept outside the focused neighborhood",
            ),
        ),
        relationships=(relationship,),
    )
    arelle_result = _arelle_result(
        concepts=(
            _concept(
                evidence_id="concept-target-revenue",
                concept=revenue.candidate_concepts[0].concept,
                label="Revenue",
                documentation="Revenue target concept",
                taxonomy=revenue.candidate_concepts[0].taxonomy,
            ),
            _concept(
                evidence_id="concept-revenue",
                concept="CustomerRevenue",
                label="Customer revenue",
                documentation="Revenue from customer contracts",
            ),
            _concept(
                evidence_id="concept-detail",
                concept="RevenueDetail",
                label="Revenue detail",
                documentation="Context for the reported revenue concept",
            ),
            _concept(
                evidence_id="concept-unrelated",
                concept="UnrelatedDisclosure",
                label="Unrelated disclosure",
                documentation="A taxonomy concept outside the focused neighborhood",
            ),
        ),
        facts=(
            ArelleFactRecord(
                evidence_id="fact-revenue",
                concept_id="concept-revenue",
                context_id="context-2025",
                unit_id="usd",
                display_value="987654321",
                numeric_value="987654321",
                is_nil=False,
                decimals="-6",
                precision=None,
                xml_lang=None,
            ),
        ),
        relationships=(relationship,),
        formula_assertions=(
            ArelleFormulaAssertionRecord(
                assertion_id="assertion-revenue",
                assertion_type="value",
                satisfied_count=1,
                unsatisfied_count=0,
                ok_message_count=1,
                warning_message_count=0,
                error_message_count=0,
            ),
        ),
        diagnostics=(
            ArelleDiagnosticRecord(
                severity="warning",
                code="xbrl.5.2.5.2:calcInconsistency",
                message="A numeric message that must not enter the packet: 987654321",
                fact_ids=("fact-revenue",),
                relationship_ids=("relationship-revenue-detail",),
            ),
        ),
    )

    packet = build_semantic_evidence_packet(
        precedence=precedence,
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
        arelle_results=(arelle_result,),
    )

    assert packet.schema_version == "1"
    assert packet.arelle_evidence_status == "available"
    assert [
        (target.metric_name, target.statement_type)
        for target in packet.targets
    ] == [("revenue", "income_statement")]
    concepts = {concept.concept: concept for concept in packet.concepts}
    assert concepts["CustomerRevenue"].component_eligible is True
    assert concepts["CustomerRevenue"].source_evidence_ids == ("concept-revenue",)
    assert concepts["CustomerRevenue"].label_source_system == "arelle_structural"
    assert (
        concepts["CustomerRevenue"].documentation_source_system
        == "arelle_structural"
    )
    assert concepts["RevenueDetail"].component_eligible is False
    assert "UnrelatedDisclosure" not in concepts
    assert packet.relationships[0].evidence_id == "relationship-revenue-detail"
    assert packet.formula_assertions[0].status == "satisfied"
    assert packet.validations[0].affected_evidence_ids == (
        "concept-revenue",
        "relationship-revenue-detail",
    )


def test_packet_excludes_period_fact_and_filing_specific_fields() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=8675309,
        arelle_fact_id="fact-revenue",
    )
    packet = build_semantic_evidence_packet(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
        arelle_results=(
            _arelle_result(
                concepts=(
                    _concept(
                        evidence_id="concept-revenue",
                        concept="CustomerRevenue",
                        label="Customer revenue",
                        documentation="Revenue from customer contracts",
                    ),
                ),
                facts=(
                    ArelleFactRecord(
                        evidence_id="fact-revenue",
                        concept_id="concept-revenue",
                        context_id="context-2025",
                        unit_id="usd",
                        display_value="987654321",
                        numeric_value="987654321",
                        is_nil=False,
                        decimals="-6",
                        precision=None,
                        xml_lang=None,
                    ),
                ),
            ),
        ),
    )

    payload = packet.to_json()

    for excluded in (
        "987654321",
        "8675309",
        "0000000001-25-000001",
        "2025-10-31",
        "2025-09-27",
        "context-2025",
        '"unit"',
        '"fiscal_period"',
        '"fiscal_year"',
        '"shadow"',
    ):
        assert excluded not in payload


def test_identical_company_packet_target_set_and_judges_share_one_request() -> None:
    packet = _basic_packet()

    groups = group_semantic_evidence_packets(
        (
            SemanticEvidencePeriod(
                company_id="0000000001",
                period_id="FY-2025",
                packet=packet,
                judge_models=(
                    "gemini-2.5-flash",
                    "gpt-5-mini",
                    "gemini-3.1-flash-lite",
                ),
            ),
            SemanticEvidencePeriod(
                company_id="0000000001",
                period_id="FY-2024",
                packet=packet,
                judge_models=(
                    "gpt-5-mini",
                    "gemini-3.1-flash-lite",
                    "gemini-2.5-flash",
                ),
            ),
        )
    )

    assert len(groups) == 1
    assert groups[0].period_ids == ("FY-2024", "FY-2025")
    assert groups[0].judge_models == (
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gpt-5-mini",
    )
    assert groups[0].recommendation_request_id.startswith(
        "semantic-recommendation:"
    )


def test_blocked_arelle_relationship_remains_visible_for_judge_context() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    target_candidate = revenue.candidate_concepts[0]
    usable = ArelleRelationshipRecord(
        evidence_id="relationship-usable",
        network_kind="calculation",
        arcrole="summation-item",
        link_role="income-statement",
        from_id="concept-target-revenue",
        to_id="concept-detail",
        order="1",
        weight="1",
        preferred_label=None,
        target_role=None,
    )
    blocked = ArelleRelationshipRecord(
        evidence_id="relationship-blocked",
        network_kind="calculation",
        arcrole="summation-item",
        link_role="income-statement",
        from_id="concept-target-revenue",
        to_id="concept-other",
        order="2",
        weight="-1",
        preferred_label=None,
        target_role=None,
    )
    diagnostic = ArelleDiagnosticRecord(
        severity="error",
        code="xbrl.calculation.invalid",
        message="Relationship validation failed",
        relationship_ids=("relationship-blocked",),
    )
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id=None,
    )
    packet = build_semantic_evidence_packet(
        precedence=_precedence_result(
            selected,
            relationships=(usable,),
            blocked_relationships=(blocked,),
            blocking_diagnostics=(diagnostic,),
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
        arelle_results=(
            _arelle_result(
                concepts=(
                    _concept(
                        evidence_id="concept-target-revenue",
                        concept=target_candidate.concept,
                        label="Revenue",
                        documentation="Revenue target concept",
                        taxonomy=target_candidate.taxonomy,
                    ),
                    _concept(
                        evidence_id="concept-detail",
                        concept="RevenueDetail",
                        label="Revenue detail",
                        documentation="Usable relationship context",
                    ),
                    _concept(
                        evidence_id="concept-other",
                        concept="OtherRevenue",
                        label="Other revenue",
                        documentation="Blocked relationship context",
                    ),
                ),
                relationships=(usable, blocked),
                diagnostics=(diagnostic,),
            ),
        ),
    )

    assert [
        (relationship.evidence_id, relationship.usable)
        for relationship in packet.relationships
    ] == [
        ("relationship-blocked", False),
        ("relationship-usable", True),
    ]
    assert packet.validations[0].affected_evidence_ids == (
        "relationship-blocked",
    )


def test_packet_marks_unavailable_arelle_evidence_without_unscoped_networks() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    unrelated = ArelleRelationshipRecord(
        evidence_id="relationship-unscoped",
        network_kind="calculation",
        arcrole="summation-item",
        link_role="balance-sheet",
        from_id="concept-assets",
        to_id="concept-liabilities",
        order="1",
        weight="1",
        preferred_label=None,
        target_role=None,
    )
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id=None,
    )

    packet = build_semantic_evidence_packet(
        precedence=_precedence_result(
            selected,
            relationships=(unrelated,),
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
    )

    assert packet.arelle_evidence_status == "unavailable"
    assert packet.relationships == ()


def test_packet_excludes_unrelated_statement_and_resource_relationships() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    target_candidate = revenue.candidate_concepts[0]
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id="fact-revenue",
    )
    relationships = (
        ArelleRelationshipRecord(
            evidence_id="relationship-income",
            network_kind="calculation",
            arcrole="summation-item",
            link_role="income-statement",
            from_id="concept-target-revenue",
            to_id="concept-income-child",
            order="1",
            weight="1",
            preferred_label=None,
            target_role=None,
        ),
        ArelleRelationshipRecord(
            evidence_id="relationship-balance",
            network_kind="calculation",
            arcrole="summation-item",
            link_role="balance-sheet",
            from_id="concept-revenue",
            to_id="concept-balance-child",
            order="1",
            weight="1",
            preferred_label=None,
            target_role=None,
        ),
        ArelleRelationshipRecord(
            evidence_id="relationship-label",
            network_kind="label",
            arcrole="concept-label",
            link_role="label-network",
            from_id="concept-target-revenue",
            to_id="label-resource",
            order=None,
            weight=None,
            preferred_label=None,
            target_role=None,
        ),
    )
    packet = build_semantic_evidence_packet(
        precedence=_precedence_result(
            selected,
            relationships=relationships,
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
        arelle_results=(
            _arelle_result(
                concepts=(
                    _concept(
                        evidence_id="concept-target-revenue",
                        concept=target_candidate.concept,
                        label="Revenue",
                        documentation="Revenue target concept",
                        taxonomy=target_candidate.taxonomy,
                    ),
                    _concept(
                        evidence_id="concept-revenue",
                        concept="CustomerRevenue",
                        label="Customer revenue",
                        documentation="Company extension revenue",
                    ),
                    _concept(
                        evidence_id="concept-income-child",
                        concept="IncomeChild",
                        label="Income child",
                        documentation="Income statement context",
                    ),
                    _concept(
                        evidence_id="concept-balance-child",
                        concept="BalanceChild",
                        label="Balance child",
                        documentation="Unrelated balance sheet context",
                    ),
                ),
                facts=(
                    ArelleFactRecord(
                        evidence_id="fact-revenue",
                        concept_id="concept-revenue",
                        context_id="context-2025",
                        unit_id="usd",
                        display_value="987654321",
                        numeric_value="987654321",
                        is_nil=False,
                        decimals="-6",
                        precision=None,
                        xml_lang=None,
                    ),
                ),
                relationships=relationships,
            ),
        ),
    )

    assert [
        relationship.evidence_id for relationship in packet.relationships
    ] == ["relationship-income"]


def test_grouping_separates_semantic_target_company_or_judge_change() -> None:
    revenue_packet = _basic_packet()
    targets = {
        target.metric_name: target for target in canonical_metric_targets(())
    }
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id=None,
    )
    different_target_packet = build_semantic_evidence_packet(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(targets["total_assets"],),
    )
    different_evidence_packet = build_semantic_evidence_packet(
        precedence=_precedence_result(
            _selected_observation(
                concept="CustomerNetRevenue",
                raw_fact_id=102,
                arelle_fact_id=None,
            )
        ),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(targets["revenue"],),
    )
    standard_judges = (
        "gpt-5-mini",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    )

    groups = group_semantic_evidence_packets(
        (
            SemanticEvidencePeriod(
                "0000000001", "base", revenue_packet, standard_judges
            ),
            SemanticEvidencePeriod(
                "0000000001",
                "target-change",
                different_target_packet,
                standard_judges,
            ),
            SemanticEvidencePeriod(
                "0000000001",
                "evidence-change",
                different_evidence_packet,
                standard_judges,
            ),
            SemanticEvidencePeriod(
                "0000000002", "company-change", revenue_packet, standard_judges
            ),
            SemanticEvidencePeriod(
                "0000000001",
                "judge-change",
                revenue_packet,
                (
                    "gpt-5-mini",
                    "gemini-3.1-flash-lite",
                    "gemini-2.0-flash",
                ),
            ),
        )
    )

    assert len(groups) == 5
    assert sorted(group.period_ids for group in groups) == [
        ("base",),
        ("company-change",),
        ("evidence-change",),
        ("judge-change",),
        ("target-change",),
    ]


def test_grouping_requires_exactly_three_distinct_judge_models() -> None:
    with pytest.raises(
        ValueError,
        match="exactly three distinct judge models",
    ):
        group_semantic_evidence_packets(
            (
                SemanticEvidencePeriod(
                    company_id="0000000001",
                    period_id="FY-2025",
                    packet=_basic_packet(),
                    judge_models=("gpt-5-mini", "gpt-5-mini", "gemini"),
                ),
            )
        )


def test_grouping_rejects_conflicting_inputs_for_the_same_company_period() -> None:
    targets = {
        target.metric_name: target for target in canonical_metric_targets(())
    }
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id=None,
    )
    different_packet = build_semantic_evidence_packet(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(targets["total_assets"],),
    )
    judges = (
        "gpt-5-mini",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    )

    with pytest.raises(ValueError, match="duplicate semantic evidence period"):
        group_semantic_evidence_packets(
            (
                SemanticEvidencePeriod(
                    "0000000001", "FY-2025", _basic_packet(), judges
                ),
                SemanticEvidencePeriod(
                    "0000000001", "FY-2025", different_packet, judges
                ),
            )
        )
    with pytest.raises(ValueError, match="duplicate semantic evidence period"):
        group_semantic_evidence_packets(
            (
                SemanticEvidencePeriod(
                    "0000000001", "FY-2025", _basic_packet(), judges
                ),
                SemanticEvidencePeriod(
                    "0000000001",
                    "FY-2025",
                    _basic_packet(),
                    (
                        "gpt-5-mini",
                        "gemini-3.1-flash-lite",
                        "gemini-2.0-flash",
                    ),
                ),
            )
        )


def test_numeric_and_filing_changes_do_not_split_a_semantic_group() -> None:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    packets = []
    for fiscal_year, raw_fact_id, value, accession, filed_date in (
        (2024, 401, "100", "0000000001-24-000001", date(2024, 10, 31)),
        (2025, 501, "250", "0000000001-25-000001", date(2025, 10, 31)),
    ):
        selected = _selected_observation(
            concept="CustomerRevenue",
            raw_fact_id=raw_fact_id,
            arelle_fact_id=None,
            fiscal_year=fiscal_year,
            value=value,
            accession_number=accession,
            filed_date=filed_date,
        )
        packets.append(
            build_semantic_evidence_packet(
                precedence=_precedence_result(selected),
                fiscal_year=fiscal_year,
                fiscal_period="FY",
                missing_targets=(revenue,),
            )
        )

    assert packets[0].content_sha256 == packets[1].content_sha256
    groups = group_semantic_evidence_packets(
        tuple(
            SemanticEvidencePeriod(
                company_id="0000000001",
                period_id=f"FY-{fiscal_year}",
                packet=packet,
                judge_models=(
                    "gpt-5-mini",
                    "gemini-3.1-flash-lite",
                    "gemini-2.5-flash",
                ),
            )
            for fiscal_year, packet in zip((2024, 2025), packets)
        )
    )
    assert len(groups) == 1


def _basic_packet() -> SemanticEvidencePacket:
    revenue = next(
        target
        for target in canonical_metric_targets(())
        if target.metric_name == "revenue"
    )
    selected = _selected_observation(
        concept="CustomerRevenue",
        raw_fact_id=101,
        arelle_fact_id="fact-revenue",
    )
    return build_semantic_evidence_packet(
        precedence=_precedence_result(selected),
        fiscal_year=2025,
        fiscal_period="FY",
        missing_targets=(revenue,),
    )


def _precedence_result(
    *selected: PrecedenceSelectedObservation,
    metadata: tuple[ConceptMetadataResolution, ...] = (),
    relationships: tuple[ArelleRelationshipRecord, ...] = (),
    blocked_relationships: tuple[ArelleRelationshipRecord, ...] = (),
    blocking_diagnostics: tuple[ArelleDiagnosticRecord, ...] = (),
) -> CompanyPrecedenceResult:
    return CompanyPrecedenceResult(
        fact_resolutions=tuple(
            FactPrecedenceResolution(
                semantic_identity=item.semantic_identity,
                selected=item,
                candidates=(),
                invalid_candidates=(),
                quarantined_candidates=(),
                equivalent_candidates=(),
            )
            for item in selected
        ),
        statement_networks=(
            (
                PrecedenceStatementNetwork(
                    identity=StatementNetworkIdentity(
                        network_kind="calculation",
                        arcrole="summation-item",
                        link_role="income-statement",
                    ),
                    source_accession_number="0000000001-25-000001",
                    source_filing_date=date(2025, 10, 31),
                    relationships=relationships,
                    blocked_relationships=blocked_relationships,
                    blocking_diagnostics=blocking_diagnostics,
                ),
            )
            if relationships or blocked_relationships
            else ()
        ),
        concept_metadata=metadata,
    )


def _selected_observation(
    *,
    concept: str,
    raw_fact_id: int,
    arelle_fact_id: str | None,
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    value: str = "987654321",
    accession_number: str = "0000000001-25-000001",
    filed_date: date = date(2025, 10, 31),
) -> PrecedenceSelectedObservation:
    fact = NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="custom",
        concept=concept,
        label=concept,
        description=f"{concept} documentation",
        unit="USD",
        value_raw=value,
        value=Decimal(value),
        start_date=date(2024, 9, 29),
        end_date=date(2025, 9, 27),
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form="10-K",
        filed_date=filed_date,
        accession_number=accession_number,
        frame="CY2025",
        source=INLINE_XBRL_SOURCE,
        is_numeric=True,
    )
    source_observation = ReconciliationSourceObservation(
        raw_fact_id=raw_fact_id,
        fact=fact,
        arelle_fact_id=arelle_fact_id,
    )
    identity = SemanticFactIdentity(
        cik=fact.cik,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        start_date=fact.start_date,
        end_date=fact.end_date,
        unit=fact.unit,
        dimensions=fact.dimensions,
        is_consolidated=fact.is_consolidated,
    )
    reconciliation = ReconciledObservation(
        semantic_identity=identity,
        outcome=RECONCILIATION_ARELLE_ONLY,
        match_kind=None,
        selected=source_observation,
        source_observations=(source_observation,),
    )
    return PrecedenceSelectedObservation(
        semantic_identity=identity,
        accession_number=fact.accession_number or "",
        filing_date=fact.filed_date or date.min,
        observation=source_observation,
        reconciliation=reconciliation,
    )


def _metadata(
    *,
    concept: str,
    label: str,
    description: str,
) -> ConceptMetadataResolution:
    return ConceptMetadataResolution(
        identity=ConceptIdentity(taxonomy="custom", concept=concept),
        fields=(
            PrecedenceMetadataField(
                name="label",
                value=label,
                source_system="arelle_structural",
                source_accession_number="0000000001-25-000001",
                source_filing_date=date(2025, 10, 31),
            ),
            PrecedenceMetadataField(
                name="description",
                value=description,
                source_system="arelle_structural",
                source_accession_number="0000000001-25-000001",
                source_filing_date=date(2025, 10, 31),
            ),
        ),
    )


def _concept(
    *,
    evidence_id: str,
    concept: str,
    label: str,
    documentation: str,
    taxonomy: str = "custom",
) -> ArelleConceptRecord:
    namespace_uri = (
        "https://fasb.org/us-gaap"
        if taxonomy == "us-gaap"
        else "https://example.com/custom"
    )
    return ArelleConceptRecord(
        evidence_id=evidence_id,
        qname=f"{{{namespace_uri}}}{concept}",
        namespace_uri=namespace_uri,
        local_name=concept,
        prefix=taxonomy,
        label=label,
        documentation=documentation,
        type_qname="{http://www.xbrl.org/2003/instance}monetaryItemType",
        base_type="monetaryItemType",
        period_type="duration",
        balance="credit",
        is_numeric=True,
        is_abstract=False,
    )


def _arelle_result(
    *,
    concepts: tuple[ArelleConceptRecord, ...] = (),
    facts: tuple[ArelleFactRecord, ...] = (),
    relationships: tuple[ArelleRelationshipRecord, ...] = (),
    formula_assertions: tuple[ArelleFormulaAssertionRecord, ...] = (),
    diagnostics: tuple[ArelleDiagnosticRecord, ...] = (),
) -> ArelleFilingResult:
    return ArelleFilingResult(
        schema_version="2",
        adapter_version="1",
        arelle_version="test",
        filing=ArelleFilingIdentity(
            cik="0000000001",
            accession_number="0000000001-25-000001",
            form="10-K",
            filing_date="2025-10-31",
            entry_point_path="filing.htm",
            source_url="https://www.sec.gov/example/filing.htm",
        ),
        status=ARELLE_RESULT_COMPLETE,
        facts=facts,
        concepts=concepts,
        contexts=(),
        units=(),
        relationships=relationships,
        formula_assertions=formula_assertions,
        diagnostics=diagnostics,
        namespaces=(),
        source_documents=(),
        record_counts=ArelleRecordCounts(),
        timings=ArelleTimingRecord(),
        content_sha256=None,
        payload_sha256="test",
        worker_pid=None,
        session_closed=True,
    )
