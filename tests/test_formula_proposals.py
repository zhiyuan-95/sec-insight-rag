from __future__ import annotations

from pathlib import Path
from decimal import Decimal

from src.analyze.xbrl_formula_proposals import default_formula_proposal_provider_configs
from src.processing.formula_proposals import (
    PROVIDER_STATUS_TARGET_ZERO,
    STATEMENT_RELATIONSHIP_CROSS,
    STATEMENT_RELATIONSHIP_SAME,
    VALIDATION_SKIP_CIRCULAR_COMPONENT,
    VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION,
    VALIDATION_SKIP_OUTSIDE_FACT_POOL,
    VALIDATION_SKIP_ZERO_TARGET_NO_EVIDENCE,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_VALIDATED,
    VALIDATION_STATUS_ZERO_EVIDENCE,
    FormulaProposalComponentResponse,
    FormulaProposalFact,
    FormulaProposalProviderResult,
    FormulaProposalResponse,
    FormulaProposalTarget,
    build_formula_proposal_contexts,
    coerce_formula_proposal_response,
    formula_context_fingerprint,
    load_formula_proposal_cache,
    provider_result_from_response,
    save_formula_proposal_cache,
    validate_formula_proposal,
)


def test_formula_proposal_provider_configs_use_gemini_and_openai_only() -> None:
    configs = default_formula_proposal_provider_configs(
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
    )

    assert [(config.provider_name, config.model_name) for config in configs] == [
        ("gemini", "gemini-2.5-flash"),
        ("openai", "gpt-4.1-mini"),
    ]


def test_formula_proposal_validator_allows_found_target_fact_components() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(
        components=(
            _component("LongTermDebtCurrent", "found current portion"),
            _component("ShortTermBorrowings", "found short-term borrowing"),
        )
    )
    facts = (
        _fact("LongTermDebtCurrent", 1, mapping_status="found_target"),
        _fact("ShortTermBorrowings", 2, mapping_status="mapped_base_metric"),
    )

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=facts,
    )

    assert validation.validation_status == VALIDATION_STATUS_VALIDATED
    assert validation.skip_reason == ""
    assert validation.matched_raw_fact_ids == (1, 2)
    assert validation.common_period_units == ("2025 FY instant USD",)


def test_formula_proposal_validator_rejects_component_outside_raw_fact_pool() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(components=(_component("CommercialPaper", "not in pool"),))

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=(_fact("LongTermDebtCurrent", 1),),
    )

    assert validation.validation_status == VALIDATION_STATUS_FAILED
    assert validation.skip_reason == VALIDATION_SKIP_OUTSIDE_FACT_POOL
    assert validation.invalid_components == ("us-gaap:CommercialPaper",)


def test_formula_proposal_validator_rejects_circular_target_component() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(components=(_component("DebtCurrent", "circular"),))

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=(_fact("DebtCurrent", 10, mapping_status="found_unmapped_target"),),
    )

    assert validation.validation_status == VALIDATION_STATUS_FAILED
    assert validation.skip_reason == VALIDATION_SKIP_CIRCULAR_COMPONENT
    assert validation.circular_components == ("us-gaap:DebtCurrent",)


def test_formula_proposal_context_hash_reuses_same_concept_set_across_periods() -> None:
    target = _target("AssetsCurrent", "assets_current")
    facts = (
        _fact("CashAndCashEquivalentsAtCarryingValue", 1, fiscal_year=2025, accession_number="a"),
        _fact("AccountsReceivableNetCurrent", 2, fiscal_year=2025, accession_number="a"),
        _fact("CashAndCashEquivalentsAtCarryingValue", 3, fiscal_year=2024, accession_number="b"),
        _fact("AccountsReceivableNetCurrent", 4, fiscal_year=2024, accession_number="b"),
    )

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)
    hashes = [
        formula_context_fingerprint(
            target=target,
            context=context,
            provider_name="test_provider",
            model_name="test_model",
        )[0]
        for context in contexts
    ]

    assert len(contexts) == 2
    assert len(set(hashes)) == 1
    assert contexts[0].period_context["fiscal_year"] != contexts[1].period_context["fiscal_year"]
    assert all(
        row["statement_relationship"] == STATEMENT_RELATIONSHIP_SAME
        for context in contexts
        for row in context.prompt_fact_pool
    )


def test_formula_proposal_contexts_filter_monetary_targets_to_currency_units() -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (
        _fact("ShortTermBorrowings", 1, unit="USD"),
        _fact("CommonStocksIncludingAdditionalPaidInCapital", 2, unit="shares"),
        _fact("DebtToAssetsRatio", 3, unit="pure"),
    )

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 1
    assert contexts[0].period_context["unit"] == "USD"
    assert [row["concept"] for row in contexts[0].prompt_fact_pool] == ["ShortTermBorrowings"]


def test_formula_proposal_contexts_fall_back_when_no_compatible_unit_exists() -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (_fact("CustomDebtDisclosure", 1, unit="pure"),)

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 1
    assert contexts[0].period_context["unit"] == "pure"


def test_formula_proposal_validator_requires_cross_statement_explanation() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(components=(_component("Revenues", ""),))
    fact = _fact("Revenues", 1, mapped_statement_type="income_statement")

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=(fact,),
        statement_relationship_by_key={fact.concept_key: STATEMENT_RELATIONSHIP_CROSS},
    )

    assert validation.validation_status == VALIDATION_STATUS_FAILED
    assert validation.skip_reason == VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION
    assert validation.invalid_components == ("us-gaap:Revenues",)


def test_formula_proposal_response_can_propose_zero_target_with_evidence() -> None:
    target = _target("DebtCurrent", "debt_current")
    response = coerce_formula_proposal_response(
        {
            "no_formula": False,
            "target_is_zero": True,
            "target_metric_name": "debt_current",
            "target_xbrl_concept": "us-gaap:DebtCurrent",
            "formula_expression": "debt_current = 0",
            "components": [
                {
                    "component_name": "short term borrowings disclosure",
                    "taxonomy": "us-gaap",
                    "concept": "ShortTermBorrowings",
                    "operator": "+",
                    "role": "same-period liability evidence supporting zero current debt review",
                    "reason": "The raw fact is present in the eligible same-period pool.",
                }
            ],
            "confidence": 0.6,
            "reason": "Current debt may be zero based on same-period borrowing evidence.",
            "uncertainty": "Requires human review before treating the target as zero.",
        }
    )
    assert isinstance(response, FormulaProposalResponse)

    result = provider_result_from_response(
        provider_name="gemini",
        model_name="gemini-2.5-flash",
        target=target,
        response=response,
    )
    validation = validate_formula_proposal(
        target=target,
        proposal=result,
        fact_pool=(_fact("ShortTermBorrowings", 22),),
    )

    assert result.provider_status == PROVIDER_STATUS_TARGET_ZERO
    assert result.target_is_zero is True
    assert result.no_formula is False
    assert validation.validation_status == VALIDATION_STATUS_ZERO_EVIDENCE
    assert validation.matched_raw_fact_ids == (22,)


def test_formula_proposal_validator_rejects_zero_target_without_evidence() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(
        components=(),
        provider_status=PROVIDER_STATUS_TARGET_ZERO,
        target_is_zero=True,
        formula_expression="debt_current = 0",
    )

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=(_fact("ShortTermBorrowings", 22),),
    )

    assert validation.validation_status == VALIDATION_STATUS_FAILED
    assert validation.skip_reason == VALIDATION_SKIP_ZERO_TARGET_NO_EVIDENCE


def test_formula_proposal_cache_round_trips_structured_success(tmp_path: Path) -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (_fact("ShortTermBorrowings", 1),)
    context = build_formula_proposal_contexts(target=target, fact_pool=facts)[0]
    formula_hash, payload = formula_context_fingerprint(
        target=target,
        context=context,
        provider_name="test_provider",
        model_name="test_model",
    )
    result = _proposal(components=(_component("ShortTermBorrowings", "same statement component"),))

    write_warning = save_formula_proposal_cache(
        cache_dir=tmp_path,
        formula_context_hash=formula_hash,
        fingerprint_payload=payload,
        result=result,
    )
    loaded, read_warning = load_formula_proposal_cache(
        cache_dir=tmp_path,
        formula_context_hash=formula_hash,
        target=target,
        provider_name="test_provider",
        model_name="test_model",
    )

    assert write_warning == ""
    assert read_warning == ""
    assert loaded is not None
    assert loaded.provider_status == "proposed"
    assert loaded.components[0].concept == "ShortTermBorrowings"


def _target(concept: str, metric_name: str) -> FormulaProposalTarget:
    return FormulaProposalTarget(
        target_metric_name=metric_name,
        target_xbrl_concept=f"us-gaap:{concept}",
        taxonomy="us-gaap",
        concept=concept,
        statement_type="balance_sheet",
    )


def _proposal(
    *,
    components: tuple[FormulaProposalComponentResponse, ...],
    provider_status: str = "proposed",
    target_is_zero: bool = False,
    formula_expression: str = "debt_current = components",
) -> FormulaProposalProviderResult:
    return FormulaProposalProviderResult(
        provider_name="test_provider",
        model_name="test_model",
        target_metric_name="debt_current",
        target_xbrl_concept="us-gaap:DebtCurrent",
        provider_status=provider_status,
        no_formula=False,
        target_is_zero=target_is_zero,
        formula_expression=formula_expression,
        components=components,
        confidence=0.8,
        reason="test",
        uncertainty="test",
    )


def _component(concept: str, role: str) -> FormulaProposalComponentResponse:
    return FormulaProposalComponentResponse(
        component_name=concept,
        taxonomy="us-gaap",
        concept=concept,
        operator="+",
        role=role,
        reason=role,
    )


def _fact(
    concept: str,
    raw_fact_id: int,
    *,
    mapping_status: str = "unknown_unmapped",
    fiscal_year: int = 2025,
    accession_number: str = "test-10k",
    mapped_statement_type: str = "balance_sheet",
    unit: str = "USD",
) -> FormulaProposalFact:
    return FormulaProposalFact(
        raw_fact_id=raw_fact_id,
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        value_numeric=Decimal("10"),
        unit=unit,
        period_type="instant",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        accession_number=accession_number,
        form="10-K",
        mapping_status=mapping_status,
        mapped_statement_type=mapped_statement_type,
    )
