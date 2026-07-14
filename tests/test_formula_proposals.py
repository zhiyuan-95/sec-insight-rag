from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest

from src.analyze import xbrl_formula_proposals as formula_provider
from src.analyze.xbrl_formula_proposals import (
    FormulaProposalProviderConfig,
    default_formula_proposal_provider_configs,
    generate_formula_proposal,
    generate_formula_proposal_batch,
)
from src.processing.formula_proposals import (
    CONSENSUS_DISAGREEMENT,
    CONSENSUS_TARGET_ZERO,
    CONSENSUS_VALIDATED,
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_NO_FORMULA,
    PROVIDER_STATUS_TARGET_ZERO,
    PROVIDER_STATUS_UNAVAILABLE,
    STATEMENT_RELATIONSHIP_CROSS,
    STATEMENT_RELATIONSHIP_SAME,
    VALIDATION_SKIP_CIRCULAR_COMPONENT,
    VALIDATION_SKIP_CROSS_STATEMENT_EXPLANATION,
    VALIDATION_SKIP_DUPLICATE_FACTS,
    VALIDATION_SKIP_OUTSIDE_FACT_POOL,
    VALIDATION_SKIP_ZERO_TARGET_NO_EVIDENCE,
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_VALIDATED,
    VALIDATION_STATUS_ZERO_EVIDENCE,
    FormulaProposalComponentResponse,
    FormulaProposalBatchResponse,
    FormulaProposalFact,
    FormulaProposalProviderResult,
    FormulaProposalResponse,
    FormulaProposalTarget,
    FormulaProposalValidationResult,
    build_formula_proposal_contexts,
    coerce_formula_proposal_batch_response,
    coerce_formula_proposal_response,
    formula_batch_group_key,
    formula_context_fingerprint,
    formula_proposal_consensus,
    load_formula_proposal_cache,
    provider_result_from_response,
    save_formula_proposal_cache,
    validate_formula_proposal,
)


def test_formula_proposal_provider_configs_use_ordered_three_model_panel() -> None:
    configs = default_formula_proposal_provider_configs(
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
    )

    assert [(config.provider_name, config.model_name) for config in configs] == [
        ("openai", "gpt-5-mini"),
        ("anthropic", "claude-sonnet-5"),
        ("gemini", "gemini-2.5-flash"),
    ]


def test_formula_proposal_provider_configs_preserve_slot_overrides() -> None:
    configs = default_formula_proposal_provider_configs(
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
        openai_model="openai-override",
        gemini_model="gemini-override",
    )

    assert [config.model_name for config in configs] == [
        "openai-override",
        "claude-sonnet-5",
        "gemini-override",
    ]


def test_formula_proposal_provider_configs_reject_anthropic_model_override() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        default_formula_proposal_provider_configs(
            gemini_api_key="gemini-key",
            openai_api_key="openai-key",
            anthropic_api_key="anthropic-key",
            anthropic_model="claude-other-model",  # type: ignore[call-arg]
        )


def test_formula_proposal_panel_sends_identical_canonical_prompt() -> None:
    configs = default_formula_proposal_provider_configs(
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
    )
    prompts: list[tuple[str, str]] = []

    def capture_prompt(prompt, schema, model):
        prompts.append((model, prompt))
        return _single_proposal_payload(_target("DebtCurrent", "debt_current"))

    for config in configs:
        result = generate_formula_proposal(
            ticker="TEST",
            cik="0000000001",
            target=_target("DebtCurrent", "debt_current"),
            fact_pool=[{"taxonomy": "us-gaap", "concept": "ShortTermBorrowings"}],
            formula_context={"context_id": "same-context"},
            provider=config,
            generate_json=capture_prompt,
        )
        assert result.provider_status == PROVIDER_STATUS_NO_FORMULA

    assert [model for model, _ in prompts] == [config.model_name for config in configs]
    assert len({prompt for _, prompt in prompts}) == 1


def test_gpt5_mini_openai_requests_omit_temperature(monkeypatch) -> None:
    payloads: list[dict[str, object]] = []
    target = _target("DebtCurrent", "debt_current")

    def fake_post_json(url, payload, *, headers, redaction_values=()):
        payloads.append(payload)
        schema_name = payload["text"]["format"]["name"]
        response = (
            {"proposals": [_single_proposal_payload(target)]}
            if schema_name.endswith("batch")
            else _single_proposal_payload(target)
        )
        return {"output_text": json.dumps(response)}

    monkeypatch.setattr(formula_provider, "_post_json", fake_post_json)
    provider = FormulaProposalProviderConfig("openai", "gpt-5-mini", "test-key")

    generate_formula_proposal(
        ticker="TEST",
        cik="0000000001",
        target=target,
        fact_pool=[],
        provider=provider,
    )
    generate_formula_proposal_batch(
        ticker="TEST",
        cik="0000000001",
        targets=[target],
        fact_pool=[],
        provider=provider,
    )

    assert len(payloads) == 2
    assert all("temperature" not in payload for payload in payloads)


def test_claude_sonnet5_single_request_uses_adaptive_medium_structured_output(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    target = _target("DebtCurrent", "debt_current")

    def fake_post_json(url, payload, *, headers, redaction_values=()):
        captured.update(
            url=url,
            payload=payload,
            headers=headers,
            redaction_values=redaction_values,
        )
        return {
            "stop_reason": "end_turn",
            "content": [
                {"type": "thinking", "thinking": "opaque", "signature": "signed"},
                {"type": "redacted_thinking", "data": "encrypted"},
                {"type": "text", "text": json.dumps(_single_proposal_payload(target))},
            ],
        }

    monkeypatch.setattr(formula_provider, "_post_json", fake_post_json)

    result = generate_formula_proposal(
        ticker="TEST",
        cik="0000000001",
        target=target,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            "anthropic",
            "claude-sonnet-5",
            "anthropic-key",
        ),
    )

    assert result.provider_status == PROVIDER_STATUS_NO_FORMULA
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"] == {
        "x-api-key": "anthropic-key",
        "anthropic-version": "2023-06-01",
    }
    assert captured["redaction_values"] == ("anthropic-key",)
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "claude-sonnet-5"
    assert payload["max_tokens"] == 8192
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"]["effort"] == "medium"
    output_format = payload["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    wire_schema = output_format["schema"]
    assert wire_schema["properties"]["confidence"] == {"type": "number"}
    assert formula_provider.FORMULA_PROPOSAL_RESPONSE_JSON_SCHEMA["properties"][
        "confidence"
    ] == {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
    }
    assert payload["system"] == (
        "Return only valid JSON for the requested XBRL formula proposal schema."
    )
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert isinstance(messages[0]["content"], str)
    assert messages[0]["content"]
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload


def test_claude_sonnet5_batch_request_uses_batch_schema(monkeypatch) -> None:
    captured_payloads: list[dict[str, object]] = []
    targets = [
        _target("AssetsCurrent", "current_assets"),
        _target("LiabilitiesCurrent", "current_liabilities"),
    ]

    def fake_post_json(url, payload, *, headers, redaction_values=()):
        captured_payloads.append(payload)
        return {
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"proposals": [_single_proposal_payload(target) for target in targets]}
                    ),
                }
            ],
        }

    monkeypatch.setattr(formula_provider, "_post_json", fake_post_json)

    results = generate_formula_proposal_batch(
        ticker="TEST",
        cik="0000000001",
        targets=targets,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            "anthropic",
            "claude-sonnet-5",
            "anthropic-key",
        ),
    )

    assert [result.provider_status for result in results] == [
        PROVIDER_STATUS_NO_FORMULA,
        PROVIDER_STATUS_NO_FORMULA,
    ]
    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    wire_schema = payload["output_config"]["format"]["schema"]
    proposal_schema = wire_schema["properties"]["proposals"]["items"]
    assert proposal_schema["properties"]["confidence"] == {"type": "number"}
    assert proposal_schema["required"] == (
        formula_provider.FORMULA_PROPOSAL_BATCH_RESPONSE_JSON_SCHEMA["properties"]
        ["proposals"]["items"]["required"]
    )
    assert payload["system"] == (
        "Return only valid JSON for the requested XBRL formula proposal batch schema."
    )


@pytest.mark.parametrize(
    "stop_reason",
    [
        "refusal",
        "max_tokens",
        "stop_sequence",
        "pause_turn",
        "tool_use",
        "model_context_window_exceeded",
        None,
        "future_stop_reason",
    ],
)
def test_claude_sonnet5_rejects_every_non_end_turn_stop_reason(
    monkeypatch,
    stop_reason: str | None,
) -> None:
    target = _target("DebtCurrent", "debt_current")

    def fake_post_json(url, payload, *, headers, redaction_values=()):
        return {
            "stop_reason": stop_reason,
            "content": [
                {"type": "text", "text": json.dumps(_single_proposal_payload(target))}
            ],
        }

    monkeypatch.setattr(formula_provider, "_post_json", fake_post_json)

    result = generate_formula_proposal(
        ticker="TEST",
        cik="0000000001",
        target=target,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            "anthropic",
            "claude-sonnet-5",
            "anthropic-key",
        ),
    )

    assert result.provider_status == PROVIDER_STATUS_FAILED
    assert result.error == "Anthropic response did not complete with end_turn"


@pytest.mark.parametrize(
    "content",
    [
        [{"type": "thinking", "thinking": "opaque", "signature": "signed"}],
        [
            {"type": "text", "text": "{}"},
            {"type": "text", "text": "{}"},
        ],
        [{"type": "text", "text": ""}],
        [{"type": "tool_use", "name": "unexpected"}],
        [{"type": "future_block", "value": "unexpected"}],
    ],
)
def test_claude_sonnet5_rejects_invalid_content_shapes(
    monkeypatch,
    content: list[dict[str, object]],
) -> None:
    target = _target("DebtCurrent", "debt_current")

    def fake_post_json(url, payload, *, headers, redaction_values=()):
        return {"stop_reason": "end_turn", "content": content}

    monkeypatch.setattr(formula_provider, "_post_json", fake_post_json)

    result = generate_formula_proposal(
        ticker="TEST",
        cik="0000000001",
        target=target,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            "anthropic",
            "claude-sonnet-5",
            "anthropic-key",
        ),
    )

    assert result.provider_status == PROVIDER_STATUS_FAILED
    assert result.error.startswith("Anthropic response")


def test_claude_http_error_redacts_secret_before_detail_truncation(monkeypatch) -> None:
    target = _target("DebtCurrent", "debt_current")
    secret = "ANTHROPIC_SECRET_THAT_MUST_NOT_LEAK"
    padding = "x" * 450
    between = "y" * (495 - len(padding) - len(secret))
    detail = f"{padding}{secret}{between}{secret}tail"

    def fail_urlopen(request, timeout):
        raise formula_provider.urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(detail.encode("utf-8")),
        )

    monkeypatch.setattr(formula_provider.urllib.request, "urlopen", fail_urlopen)

    result = generate_formula_proposal(
        ticker="TEST",
        cik="0000000001",
        target=target,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            "anthropic",
            "claude-sonnet-5",
            secret,
        ),
    )

    assert result.provider_status == PROVIDER_STATUS_FAILED
    assert secret not in result.error
    assert secret[:12] not in result.error
    assert "[REDACTED]" in result.error


@pytest.mark.parametrize("batch", [False, True])
def test_claude_failure_boundary_redacts_secret_for_single_and_batch(
    monkeypatch,
    batch: bool,
) -> None:
    target = _target("DebtCurrent", "debt_current")
    secret = "ANTHROPIC_SECRET_THAT_MUST_NOT_LEAK"

    def fail_post_json(url, payload, *, headers, redaction_values=()):
        raise RuntimeError(f"transport failed with credential {secret}")

    monkeypatch.setattr(formula_provider, "_post_json", fail_post_json)
    provider = FormulaProposalProviderConfig("anthropic", "claude-sonnet-5", secret)

    if batch:
        results = generate_formula_proposal_batch(
            ticker="TEST",
            cik="0000000001",
            targets=[target],
            fact_pool=[],
            provider=provider,
        )
    else:
        results = (
            generate_formula_proposal(
                ticker="TEST",
                cik="0000000001",
                target=target,
                fact_pool=[],
                provider=provider,
            ),
        )

    assert all(result.provider_status == PROVIDER_STATUS_FAILED for result in results)
    assert all(secret not in result.error for result in results)
    assert all("[REDACTED]" in result.error for result in results)


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


def test_formula_proposal_validator_uses_actual_dates_and_prefers_dimensionless_facts() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(
        components=(
            _component("LongTermDebtCurrent", "current debt"),
            _component("CommercialPaper", "short-term borrowing"),
        )
    )
    prior_period = date(2025, 9, 27)
    current_period = date(2026, 3, 28)
    facts = (
        _fact("LongTermDebtCurrent", 1, end_date=prior_period),
        _fact("LongTermDebtCurrent", 2, end_date=current_period),
        _fact("CommercialPaper", 3, end_date=prior_period),
        _fact("CommercialPaper", 4, end_date=prior_period, has_dimensions=True),
        _fact("CommercialPaper", 5, end_date=current_period),
        _fact("CommercialPaper", 6, end_date=current_period, has_dimensions=True),
    )

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=facts,
    )

    assert validation.validation_status == VALIDATION_STATUS_VALIDATED
    assert validation.skip_reason == ""
    assert validation.matched_raw_fact_ids == (1, 2, 3, 5)
    assert validation.common_period_units == (
        "2025-09-27 instant USD",
        "2026-03-28 instant USD",
    )


def test_formula_proposal_validator_rejects_true_same_date_dimensionless_duplicates() -> None:
    target = _target("DebtCurrent", "debt_current")
    proposal = _proposal(
        components=(
            _component("LongTermDebtCurrent", "current debt"),
            _component("CommercialPaper", "short-term borrowing"),
        )
    )
    end_date = date(2026, 3, 28)
    facts = (
        _fact("LongTermDebtCurrent", 1, end_date=end_date),
        _fact("LongTermDebtCurrent", 2, end_date=end_date),
        _fact("CommercialPaper", 3, end_date=end_date),
    )

    validation = validate_formula_proposal(
        target=target,
        proposal=proposal,
        fact_pool=facts,
    )

    assert validation.validation_status == VALIDATION_STATUS_FAILED
    assert validation.skip_reason == VALIDATION_SKIP_DUPLICATE_FACTS
    assert validation.common_period_units == ("2026-03-28 instant USD",)


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


def test_formula_proposal_contexts_group_same_concept_pool_across_periods() -> None:
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

    assert len(contexts) == 1
    assert len(set(hashes)) == 1
    assert contexts[0].period_context["period_coverage"] == "10-K periods: 2025 FY, 2024 FY"
    assert len(contexts[0].period_context["period_contexts"]) == 2
    assert all(
        row["statement_relationship"] == STATEMENT_RELATIONSHIP_SAME
        for context in contexts
        for row in context.prompt_fact_pool
    )


def test_formula_proposal_contexts_keep_different_concept_pools_separate() -> None:
    target = _target("AssetsCurrent", "assets_current")
    facts = (
        _fact("CashAndCashEquivalentsAtCarryingValue", 1, fiscal_year=2025, accession_number="a"),
        _fact("AccountsReceivableNetCurrent", 2, fiscal_year=2025, accession_number="a"),
        _fact("CashAndCashEquivalentsAtCarryingValue", 3, fiscal_year=2024, accession_number="b"),
    )

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 2
    assert [context.period_context["period_coverage"] for context in contexts] == [
        "10-K periods: 2025 FY",
        "10-K periods: 2024 FY",
    ]
    assert [len(context.prompt_fact_pool) for context in contexts] == [2, 1]


def test_formula_batch_response_coerces_multiple_target_payload() -> None:
    response = coerce_formula_proposal_batch_response(
        {
            "proposals": [
                {
                    "no_formula": False,
                    "target_is_zero": False,
                    "target_metric_name": "current_assets",
                    "target_xbrl_concept": "us-gaap:AssetsCurrent",
                    "formula_expression": "current_assets = us-gaap:CashAndCashEquivalentsAtCarryingValue",
                    "components": [
                        {
                            "component_name": "cash",
                            "taxonomy": "us-gaap",
                            "concept": "CashAndCashEquivalentsAtCarryingValue",
                            "operator": "+",
                            "role": "current asset component",
                            "reason": "same statement raw fact",
                        }
                    ],
                    "confidence": 0.7,
                    "reason": "test",
                    "uncertainty": "review",
                },
                {
                    "no_formula": True,
                    "target_is_zero": False,
                    "target_metric_name": "accounts_receivable",
                    "target_xbrl_concept": "us-gaap:AccountsReceivableNetCurrent",
                    "formula_expression": "",
                    "components": [],
                    "confidence": 0.2,
                    "reason": "insufficient facts",
                    "uncertainty": "review",
                },
            ]
        }
    )

    assert isinstance(response, FormulaProposalBatchResponse)
    assert [proposal.target_metric_name for proposal in response.proposals] == [
        "current_assets",
        "accounts_receivable",
    ]


def test_generate_formula_proposal_batch_reorders_results_by_target_identity() -> None:
    targets = [
        _target("AssetsCurrent", "current_assets"),
        _target("LiabilitiesCurrent", "current_liabilities"),
    ]
    payload = {
        "proposals": [
            _batch_proposal_payload(targets[1]),
            _batch_proposal_payload(targets[0]),
        ]
    }

    results = generate_formula_proposal_batch(
        ticker="TEST",
        cik="0000000001",
        targets=targets,
        fact_pool=[],
        provider=_batch_provider(),
        generate_json=lambda prompt, schema, model: payload,
    )

    assert [result.target_metric_name for result in results] == [
        "current_assets",
        "current_liabilities",
    ]


@pytest.mark.parametrize(
    ("case", "error_match"),
    [
        ("non_object", "non-object payload"),
        ("omitted", "returned 1 proposal"),
        ("duplicate", "duplicate target"),
        ("unexpected", "unexpected target"),
    ],
)
def test_generate_formula_proposal_batch_rejects_unusable_target_sets(
    case: str,
    error_match: str,
) -> None:
    targets = [
        _target("AssetsCurrent", "current_assets"),
        _target("LiabilitiesCurrent", "current_liabilities"),
    ]
    payload: object
    if case == "non_object":
        payload = []
    else:
        proposals = [_batch_proposal_payload(targets[0])]
        if case == "duplicate":
            proposals.append(_batch_proposal_payload(targets[0]))
        elif case == "unexpected":
            proposals.append(
                _batch_proposal_payload(_target("Equity", "stockholders_equity"))
            )
        payload = {"proposals": proposals}

    with pytest.raises(ValueError, match=error_match):
        generate_formula_proposal_batch(
            ticker="TEST",
            cik="0000000001",
            targets=targets,
            fact_pool=[],
            provider=_batch_provider(),
            generate_json=lambda prompt, schema, model: payload,
        )


def test_generate_formula_proposal_batch_reports_provider_exception_per_target() -> None:
    targets = [
        _target("AssetsCurrent", "current_assets"),
        _target("LiabilitiesCurrent", "current_liabilities"),
    ]

    def fail_generation(prompt, schema, model):
        raise RuntimeError("provider unavailable during test")

    results = generate_formula_proposal_batch(
        ticker="TEST",
        cik="0000000001",
        targets=targets,
        fact_pool=[],
        provider=_batch_provider(),
        generate_json=fail_generation,
    )

    assert [result.provider_status for result in results] == [
        PROVIDER_STATUS_FAILED,
        PROVIDER_STATUS_FAILED,
    ]


def test_generate_formula_proposal_batch_reports_missing_api_key_per_target() -> None:
    targets = [
        _target("AssetsCurrent", "current_assets"),
        _target("LiabilitiesCurrent", "current_liabilities"),
    ]

    results = generate_formula_proposal_batch(
        ticker="TEST",
        cik="0000000001",
        targets=targets,
        fact_pool=[],
        provider=FormulaProposalProviderConfig(
            provider_name="test_provider",
            model_name="test_model",
            api_key=None,
        ),
    )

    assert [result.provider_status for result in results] == [
        PROVIDER_STATUS_UNAVAILABLE,
        PROVIDER_STATUS_UNAVAILABLE,
    ]


def test_formula_batch_group_key_allows_same_statement_contexts_only() -> None:
    assets_target = _target("AssetsCurrent", "current_assets")
    receivables_target = _target("AccountsReceivableNetCurrent", "accounts_receivable")
    revenue_target = FormulaProposalTarget(
        target_metric_name="revenue",
        target_xbrl_concept="us-gaap:Revenues",
        taxonomy="us-gaap",
        concept="Revenues",
        statement_type="income_statement",
    )
    facts = (
        _fact("CashAndCashEquivalentsAtCarryingValue", 1),
        _fact("AccountsReceivableNetCurrent", 2),
    )
    revenue_facts = (
        _fact("Revenues", 3, period_type="duration", mapped_statement_type="income_statement"),
        _fact("CostOfRevenue", 4, period_type="duration", mapped_statement_type="income_statement"),
    )

    assets_context = build_formula_proposal_contexts(target=assets_target, fact_pool=facts)[0]
    receivables_context = build_formula_proposal_contexts(target=receivables_target, fact_pool=facts)[0]
    revenue_context = build_formula_proposal_contexts(target=revenue_target, fact_pool=revenue_facts)[0]

    assert formula_batch_group_key(assets_context) == formula_batch_group_key(receivables_context)
    assert formula_batch_group_key(assets_context) != formula_batch_group_key(revenue_context)


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


def test_formula_proposal_contexts_keep_primary_monetary_unit_per_period() -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (
        _fact("DebtInstrumentFaceAmount", 1, unit="EUR"),
        _fact("ShortTermBorrowings", 2, unit="USD"),
        _fact("CommercialPaper", 3, unit="USD"),
    )

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 1
    assert contexts[0].period_context["unit"] == "USD"
    assert [row["concept"] for row in contexts[0].prompt_fact_pool] == [
        "CommercialPaper",
        "ShortTermBorrowings",
    ]


def test_formula_proposal_contexts_keep_only_available_monetary_unit() -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (_fact("DebtInstrumentFaceAmount", 1, unit="EUR"),)

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 1
    assert contexts[0].period_context["unit"] == "EUR"
    assert [row["concept"] for row in contexts[0].prompt_fact_pool] == ["DebtInstrumentFaceAmount"]


def test_formula_proposal_contexts_choose_primary_monetary_unit_per_period() -> None:
    target = _target("DebtCurrent", "debt_current")
    facts = (
        _fact("ShortTermBorrowings", 1, unit="USD", fiscal_year=2025, accession_number="a"),
        _fact("DebtInstrumentFaceAmount", 2, unit="EUR", fiscal_year=2025, accession_number="a"),
        _fact("DebtInstrumentFaceAmount", 3, unit="EUR", fiscal_year=2024, accession_number="b"),
    )

    contexts = build_formula_proposal_contexts(target=target, fact_pool=facts)

    assert len(contexts) == 2
    assert [context.period_context["unit"] for context in contexts] == ["USD", "EUR"]


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


def test_formula_proposal_consensus_returns_matching_formula_bloc() -> None:
    proposals = (
        _proposal(
            model_name="gpt-5-mini",
            components=(
                _component("ShortTermBorrowings", "component"),
                _component("LongTermDebtCurrent", "component"),
            ),
        ),
        _proposal(
            model_name="claude-sonnet-5",
            components=(
                _component("LongTermDebtCurrent", "component"),
                _component("ShortTermBorrowings", "component"),
            ),
        ),
        _proposal(
            model_name="gemini-2.5-flash",
            components=(_component("FinanceLeaseLiabilityCurrent", "component"),),
        ),
    )
    validations = tuple(_validation(VALIDATION_STATUS_VALIDATED) for _ in proposals)

    consensus = formula_proposal_consensus(proposals, validations)

    assert consensus.label == CONSENSUS_VALIDATED
    assert consensus.validated_vote_count == 2
    assert consensus.agreeing_result_indexes == (0, 1)
    assert consensus.validated_outcome_count == 2
    assert consensus.formula_signature == (
        ("+", "us-gaap", "longtermdebtcurrent"),
        ("+", "us-gaap", "shorttermborrowings"),
    )


def test_formula_proposal_consensus_returns_validated_zero_bloc() -> None:
    proposals = (
        _proposal(
            model_name="gpt-5-mini",
            components=(_component("ShortTermBorrowings", "zero evidence"),),
            provider_status=PROVIDER_STATUS_TARGET_ZERO,
            target_is_zero=True,
            formula_expression="debt_current = 0",
        ),
        _proposal(
            model_name="claude-sonnet-5",
            components=(_component("LongTermDebtCurrent", "zero evidence"),),
            provider_status=PROVIDER_STATUS_TARGET_ZERO,
            target_is_zero=True,
            formula_expression="debt_current = 0",
        ),
        _proposal(
            model_name="gemini-2.5-flash",
            components=(_component("FinanceLeaseLiabilityCurrent", "component"),),
        ),
    )
    validations = (
        _validation(VALIDATION_STATUS_ZERO_EVIDENCE),
        _validation(VALIDATION_STATUS_ZERO_EVIDENCE),
        _validation(VALIDATION_STATUS_VALIDATED),
    )

    consensus = formula_proposal_consensus(proposals, validations)

    assert consensus.label == CONSENSUS_TARGET_ZERO
    assert consensus.validated_vote_count == 2
    assert consensus.agreeing_result_indexes == (0, 1)
    assert consensus.formula_signature == ()


def test_formula_proposal_consensus_exposes_unresolved_validated_outcomes() -> None:
    proposals = (
        _proposal(
            model_name="gpt-5-mini",
            components=(_component("ShortTermBorrowings", "component"),),
        ),
        _proposal(
            model_name="claude-sonnet-5",
            components=(_component("LongTermDebtCurrent", "component"),),
        ),
        _proposal(
            model_name="gemini-2.5-flash",
            components=(),
            provider_status=PROVIDER_STATUS_NO_FORMULA,
            no_formula=True,
        ),
    )
    validations = (
        _validation(VALIDATION_STATUS_VALIDATED),
        _validation(VALIDATION_STATUS_VALIDATED),
        _validation(VALIDATION_STATUS_FAILED),
    )

    consensus = formula_proposal_consensus(proposals, validations)

    assert consensus.label == CONSENSUS_DISAGREEMENT
    assert consensus.validated_vote_count == 1
    assert consensus.agreeing_result_indexes == ()
    assert consensus.validated_outcome_count == 2


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


def _batch_provider() -> FormulaProposalProviderConfig:
    return FormulaProposalProviderConfig(
        provider_name="test_provider",
        model_name="test_model",
        api_key="test-key",
    )


def _batch_proposal_payload(target: FormulaProposalTarget) -> dict[str, object]:
    return {
        "no_formula": True,
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "reason": "No supported formula in the supplied fact pool.",
        "uncertainty": "Review required.",
    }


def _single_proposal_payload(target: FormulaProposalTarget) -> dict[str, object]:
    return {
        "no_formula": True,
        "target_is_zero": False,
        "target_metric_name": target.target_metric_name,
        "target_xbrl_concept": target.target_xbrl_concept,
        "formula_expression": "",
        "components": [],
        "confidence": 0.0,
        "reason": "No supported formula in the supplied fact pool.",
        "uncertainty": "Review required.",
    }


def _proposal(
    *,
    components: tuple[FormulaProposalComponentResponse, ...],
    provider_status: str = "proposed",
    target_is_zero: bool = False,
    formula_expression: str = "debt_current = components",
    provider_name: str = "test_provider",
    model_name: str = "test_model",
    no_formula: bool = False,
) -> FormulaProposalProviderResult:
    return FormulaProposalProviderResult(
        provider_name=provider_name,
        model_name=model_name,
        target_metric_name="debt_current",
        target_xbrl_concept="us-gaap:DebtCurrent",
        provider_status=provider_status,
        no_formula=no_formula,
        target_is_zero=target_is_zero,
        formula_expression=formula_expression,
        components=components,
        confidence=0.8,
        reason="test",
        uncertainty="test",
    )


def _validation(status: str) -> FormulaProposalValidationResult:
    return FormulaProposalValidationResult(
        validation_status=status,
        skip_reason="",
        valid_component_count=1,
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
    fiscal_period: str = "FY",
    accession_number: str = "test-10k",
    mapped_statement_type: str = "balance_sheet",
    unit: str = "USD",
    period_type: str = "instant",
    form: str = "10-K",
    start_date: date | None = None,
    end_date: date | None = None,
    has_dimensions: bool = False,
) -> FormulaProposalFact:
    return FormulaProposalFact(
        raw_fact_id=raw_fact_id,
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        value_numeric=Decimal("10"),
        unit=unit,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        accession_number=accession_number,
        form=form,
        start_date=start_date,
        end_date=end_date,
        has_dimensions=has_dimensions,
        mapping_status=mapping_status,
        mapped_statement_type=mapped_statement_type,
    )
