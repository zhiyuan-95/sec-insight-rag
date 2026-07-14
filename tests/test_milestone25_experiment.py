import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

from src.config import Settings
from src.ingestion import FilingMetadata
from src.processing import NormalizedFact
from src.processing.formula_proposals import (
    VALIDATION_STATUS_FAILED,
    VALIDATION_STATUS_NOT_APPLICABLE,
    VALIDATION_STATUS_VALIDATED,
    VALIDATION_STATUS_ZERO_EVIDENCE,
    FormulaProposalComponentResponse,
    FormulaProposalContext,
    FormulaProposalProviderResult,
    FormulaProposalTarget,
    FormulaProposalValidationResult,
    formula_proposal_consensus,
)
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    ConceptMappingRecord,
    ConceptMappingRepository,
    FilingRecord,
    FilingRepository,
    FinancialMetric,
    FinancialMetricRepository,
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    RawFactRepository,
    connect_sqlite,
    initialize_database,
)


def _load_experiment_module() -> ModuleType:
    module_path = Path("experiments/MS2_5/milestone25_live_sec_inspection.py")
    spec = importlib.util.spec_from_file_location("milestone25_live_sec_inspection", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report_section(report: str, start: str, end: str | None = None) -> str:
    section = report.split(start, 1)[1]
    if end is not None:
        section = section.split(end, 1)[0]
    return section


def _assert_formula_progress_output(output: str) -> None:
    assert "[formula proposals]" in output
    assert "missing target(s) found" in output
    assert "Missing targets selected:" in output
    assert "Handling missing target" not in output
    assert "Prepared context" not in output
    assert "target-context assignment(s) across" in output
    assert "Formula proposal workload:" in output
    assert "provider-context batch slot(s)" in output
    assert "Provider workload" in output
    assert "Live batch request 1/" in output
    assert "Formula proposal generation complete:" in output
    _assert_report_generation_output(output)
    assert "reused cached recommendation" not in output
    assert "reused identical context from this run" not in output


def _assert_report_generation_output(output: str, report_path: Path | None = None) -> None:
    assert "Report generation complete:" in output
    assert " second(s); saved report: " in output
    if report_path is not None:
        assert str(report_path) in output
    assert "# Plan 2.5 Target Mapping Report" not in output


def test_milestone25_formula_provider_panel_uses_claude_sonnet5_slot() -> None:
    experiment = _load_experiment_module()
    settings = Settings.model_validate(
        {
            "Gemini_API_KEY": "gemini-key",
            "OPENAI_API_KEY": "openai-key",
            "claude-api-key": "anthropic-key",
        }
    )

    providers = experiment._formula_proposal_provider_configs(settings)

    assert [(provider.provider_name, provider.model_name) for provider in providers] == [
        ("openai", "gpt-5-mini"),
        ("anthropic", "claude-sonnet-5"),
        ("gemini", "gemini-2.5-flash"),
    ]
    assert [provider.api_key for provider in providers] == [
        "openai-key",
        "anthropic-key",
        "gemini-key",
    ]


def test_milestone25_formula_rows_collapse_same_recommended_components() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "debt_current = LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.90",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "debt_current = LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.90",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "period_context": "10-Q periods: 2021 Q1 - 2025 Q4 / instant / USD / 10-Q",
                "forms": "10-Q",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validated_component_pool",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
        ],
    }

    formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )
    quarterly_formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-Q",
    )
    assert formula_rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": "2024-2025",
            "Providers": "gemini-2.5-flash; gpt-4.1-mini",
            "Provider period coverage": (
                "gemini-2.5-flash: 2024-2025; gpt-4.1-mini: 2024-2025"
            ),
            "LLM result count": 4,
            "Formula": "debt_current = LongTermDebtCurrent",
            "Validation status": "validated_component_pool",
            "Confidence": "0.80; 0.90",
            "Reason": "same component evidence",
        }
    ]
    assert quarterly_formula_rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": (
                "2021 q1 - 2021 q3, 2022 q1 - 2022 q3, 2023 q1 - 2023 q3, "
                "2024 q1 - 2024 q3, 2025 q1 - 2025 q3"
            ),
            "Providers": "gemini-2.5-flash",
            "Provider period coverage": (
                "gemini-2.5-flash: 2021 q1 - 2021 q3, 2022 q1 - 2022 q3, "
                "2023 q1 - 2023 q3, 2024 q1 - 2024 q3, 2025 q1 - 2025 q3"
            ),
            "LLM result count": 1,
            "Formula": "debt_current = LongTermDebtCurrent",
            "Validation status": "validated_component_pool",
            "Confidence": "0.80",
            "Reason": "same component evidence",
        }
    ]
    assert "Recommendation" not in formula_rows[0]
    assert "Target concept" not in formula_rows[0]
    assert "Components" not in formula_rows[0]
    assert "Components" not in quarterly_formula_rows[0]
    assert "/" not in formula_rows[0]["Period context"]
    assert "/" not in quarterly_formula_rows[0]["Period context"]
    assert "q4" not in quarterly_formula_rows[0]["Period context"]


def test_milestone25_formula_rows_do_not_overlap_when_provider_periods_disagree() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:CommercialPaper",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "commercial paper evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:OtherLiabilitiesCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.70",
                "reason": "other liabilities evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent, + us-gaap:CommercialPaper",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "commercial paper evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2022 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "long-term debt evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2022 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "proposed",
                "formula_expression": "ignored",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.95",
                "reason": "long-term debt evidence",
            },
        ],
    }

    formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )
    assert [row["Period context"] for row in formula_rows] == [
        "2024-2025",
        "2025",
        "2022-2024",
    ]
    assert "2021-2024" not in [row["Period context"] for row in formula_rows]
    assert formula_rows[0]["Providers"] == "gemini-2.5-flash"
    assert formula_rows[0]["Provider period coverage"] == "gemini-2.5-flash: 2024-2025"
    assert formula_rows[0]["LLM result count"] == 2
    assert formula_rows[0]["Formula"] == "debt_current = LongTermDebtCurrent + CommercialPaper"
    assert formula_rows[1]["Providers"] == "gpt-4.1-mini"
    assert formula_rows[1]["Provider period coverage"] == "gpt-4.1-mini: 2025"
    assert formula_rows[1]["LLM result count"] == 1
    assert formula_rows[1]["Formula"] == "debt_current = LongTermDebtCurrent + OtherLiabilitiesCurrent"
    assert formula_rows[2]["Providers"] == "gpt-4.1-mini; gemini-2.5-flash"
    assert formula_rows[2]["Provider period coverage"] == (
        "gpt-4.1-mini: 2022-2024; gemini-2.5-flash: 2022-2023"
    )
    assert formula_rows[2]["LLM result count"] == 5
    assert formula_rows[2]["Formula"] == "debt_current = LongTermDebtCurrent"
    assert all("Components" not in row for row in formula_rows)


def test_milestone25_formula_rows_group_same_zero_formula_with_different_evidence() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "capital_expenditure",
                "statement_type": "cash_flow_statement",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "capital_expenditure",
                "target_primary_statement": "cash_flow_statement",
                "period_context": "10-K periods: 2025 FY / duration / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "target_zero",
                "formula_expression": "capital_expenditure = 0",
                "components": "",
                "validation_status": "validation_failed",
                "confidence": "0.90",
                "reason": "no capital expenditure facts",
                "context_id": "annual-2025",
                "formula_context_hash": "gemini-hash",
            },
            {
                "target_metric_name": "capital_expenditure",
                "target_primary_statement": "cash_flow_statement",
                "period_context": "10-K periods: 2024 FY / duration / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "target_zero",
                "formula_expression": "target = 0",
                "components": "+ us-gaap:PaymentsToAcquireProductiveAssets",
                "validation_status": "validation_failed",
                "confidence": "0.80",
                "reason": "absence of PP&E acquisition payments",
                "context_id": "annual-2024",
                "formula_context_hash": "openai-hash",
            },
        ],
    }

    formula_rows = experiment._proposed_formula_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )

    assert formula_rows == [
        {
            "Metric": "capital_expenditure",
            "Statement": "cash_flow_statement",
            "Period context": "2024-2025",
            "Providers": "gemini-2.5-flash; gpt-4.1-mini",
            "Provider period coverage": (
                "gemini-2.5-flash: 2025; gpt-4.1-mini: 2024"
            ),
            "LLM result count": 2,
            "Formula": "capital_expenditure = 0",
            "Validation status": "validation_failed",
            "Confidence": "0.90; 0.80",
            "Reason": "no capital expenditure facts; absence of PP&E acquisition payments",
        }
    ]


def test_milestone25_provider_outcome_gap_rows_show_non_recommendations() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "proposed",
                "formula_expression": "DebtCurrent = + us-gaap:LongTermDebtCurrent",
                "components": "+ us-gaap:LongTermDebtCurrent",
                "validation_status": "validation_failed",
                "confidence": "0.80",
                "reason": "same component evidence",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "no_formula",
                "formula_expression": "",
                "components": "",
                "validation_status": "not_applicable",
                "validation_skip_reason": "no_formula",
                "confidence": "0.20",
                "reason": "insufficient same-period debt facts",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "model_name": "gemini-2.5-flash",
                "provider_status": "provider_failed",
                "formula_expression": "",
                "components": "",
                "validation_status": "not_applicable",
                "validation_skip_reason": "provider_failed",
                "confidence": "0.00",
                "error": "test provider failure",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "period_context": "10-K periods: 2024 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "model_name": "gpt-4.1-mini",
                "provider_status": "no_formula",
                "formula_expression": "",
                "components": "",
                "validation_status": "not_applicable",
                "validation_skip_reason": "no_formula",
                "confidence": "0.10",
                "reason": "no support",
            },
        ],
    }

    rows = experiment._formula_provider_outcome_gap_rows_for_missing_targets(
        snapshot,
        form_type="10-K",
    )

    assert rows == [
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": "2025",
            "Recommendation coverage": "partial_model_recommendation",
            "Model outcomes": "gemini-2.5-flash=proposed/validation_failed; gpt-4.1-mini=no_formula/not_applicable",
            "Non-recommendation detail": "gpt-4.1-mini: no_formula - insufficient same-period debt facts",
        },
        {
            "Metric": "debt_current",
            "Statement": "balance_sheet",
            "Period context": "2024",
            "Recommendation coverage": "no_formula_recommendation",
            "Model outcomes": "gemini-2.5-flash=provider_failed/not_applicable; gpt-4.1-mini=no_formula/not_applicable",
            "Non-recommendation detail": "gemini-2.5-flash: provider_failed - test provider failure; gpt-4.1-mini: no_formula - no support",
        },
    ]


def test_milestone25_summary_recommendation_returns_two_of_three_formula() -> None:
    experiment = _load_experiment_module()
    target = _summary_target()
    context = _summary_context()
    proposals = (
        _summary_proposal("gpt-5-mini", "ShortTermBorrowings"),
        _summary_proposal("claude-sonnet-5", "ShortTermBorrowings"),
        _summary_proposal("gemini-2.5-flash", "LongTermDebtCurrent"),
    )
    validations = tuple(_summary_validation(VALIDATION_STATUS_VALIDATED) for _ in proposals)

    rows = experiment._formula_proposal_recommendation_rows(
        target=target,
        context=context,
        proposals=proposals,
        validations=validations,
        consensus=formula_proposal_consensus(proposals, validations),
    )

    assert rows == [
        {
            "form_key": "10-K",
            "period_key": "2025",
            "form": "10-K",
            "target_metric_name": "debt_current",
            "target_primary_statement": "balance_sheet",
            "period_context": "2025",
            "recommendation": "formula",
            "formula_or_value": "debt_current = ShortTermBorrowings",
            "validated_votes": "2/3",
            "agreeing_models": "gpt-5-mini; claude-sonnet-5",
            "review_reason": "",
        }
    ]


def test_milestone25_summary_recommendation_returns_two_of_three_zero() -> None:
    experiment = _load_experiment_module()
    target = _summary_target()
    context = _summary_context()
    proposals = (
        _summary_proposal("gpt-5-mini", "ShortTermBorrowings", target_zero=True),
        _summary_proposal("claude-sonnet-5", "LongTermDebtCurrent", target_zero=True),
        _summary_proposal("gemini-2.5-flash", "FinanceLeaseLiabilityCurrent"),
    )
    validations = (
        _summary_validation(VALIDATION_STATUS_ZERO_EVIDENCE),
        _summary_validation(VALIDATION_STATUS_ZERO_EVIDENCE),
        _summary_validation(VALIDATION_STATUS_VALIDATED),
    )

    rows = experiment._formula_proposal_recommendation_rows(
        target=target,
        context=context,
        proposals=proposals,
        validations=validations,
        consensus=formula_proposal_consensus(proposals, validations),
    )

    assert rows[0]["recommendation"] == "zero"
    assert rows[0]["formula_or_value"] == "0"
    assert rows[0]["validated_votes"] == "2/3"
    assert rows[0]["agreeing_models"] == "gpt-5-mini; claude-sonnet-5"
    assert rows[0]["review_reason"] == ""


def test_milestone25_summary_recommendation_explains_unresolved_outcomes() -> None:
    experiment = _load_experiment_module()
    target = _summary_target()
    context = _summary_context()
    proposals = (
        _summary_proposal("gpt-5-mini", "ShortTermBorrowings"),
        _summary_proposal("claude-sonnet-5", "LongTermDebtCurrent", target_zero=True),
        _summary_proposal("gemini-2.5-flash", "", failed=True),
    )
    validations = (
        _summary_validation(VALIDATION_STATUS_VALIDATED),
        _summary_validation(VALIDATION_STATUS_ZERO_EVIDENCE),
        _summary_validation(VALIDATION_STATUS_NOT_APPLICABLE),
    )

    rows = experiment._formula_proposal_recommendation_rows(
        target=target,
        context=context,
        proposals=proposals,
        validations=validations,
        consensus=formula_proposal_consensus(proposals, validations),
    )

    assert rows[0]["recommendation"] == "review_required"
    assert rows[0]["formula_or_value"] == ""
    assert rows[0]["validated_votes"] == "1/3"
    assert rows[0]["agreeing_models"] == ""
    assert rows[0]["review_reason"] == (
        "provider_failed; model_disagreement; no_validated_consensus"
    )


def test_milestone25_summary_recommendation_reports_unavailable_and_invalid_votes() -> None:
    experiment = _load_experiment_module()
    target = _summary_target()
    context = _summary_context()
    proposals = (
        _summary_proposal("gpt-5-mini", "ShortTermBorrowings"),
        _summary_proposal("claude-sonnet-5", "LongTermDebtCurrent"),
        _summary_proposal("gemini-2.5-flash", "", unavailable=True),
    )
    validations = (
        _summary_validation(VALIDATION_STATUS_VALIDATED),
        _summary_validation(VALIDATION_STATUS_FAILED),
        _summary_validation(VALIDATION_STATUS_NOT_APPLICABLE),
    )

    rows = experiment._formula_proposal_recommendation_rows(
        target=target,
        context=context,
        proposals=proposals,
        validations=validations,
        consensus=formula_proposal_consensus(proposals, validations),
    )

    assert rows[0]["recommendation"] == "review_required"
    assert rows[0]["validated_votes"] == "1/3"
    assert rows[0]["review_reason"] == (
        "provider_unavailable; validation_failed; no_validated_consensus"
    )


def test_milestone25_summary_recommendation_keeps_no_context_target_visible() -> None:
    experiment = _load_experiment_module()

    rows = experiment._formula_review_required_recommendation_rows(
        (_summary_target(),),
        reason="no_eligible_period_context",
    )

    assert rows[0]["form_key"] == experiment.NOT_AVAILABLE_FORM_KEY
    assert rows[0]["period_key"] == experiment.NOT_AVAILABLE_PERIOD_KEY
    assert rows[0]["form"] == "not available"
    assert rows[0]["period_context"] == "not available"
    assert rows[0]["recommendation"] == "review_required"
    assert rows[0]["review_reason"] == "no_eligible_period_context"


def test_milestone25_summary_recommendation_keeps_empty_fact_pool_targets_visible(
    tmp_path: Path,
) -> None:
    experiment = _load_experiment_module()
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        initialize_database(connection)
        snapshot = experiment._formula_proposal_snapshot(
            connection,
            ticker="TEST",
            cik="0000000001",
            company_id=1,
            target_raw_fact_coverage=_formula_batch_target_rows(experiment)[:1],
            enabled=True,
            settings=None,
            target_limit=None,
        )

    assert snapshot["diagnostics"] == []
    assert snapshot["recommendations"] == [
        {
            "form_key": experiment.NOT_AVAILABLE_FORM_KEY,
            "period_key": experiment.NOT_AVAILABLE_PERIOD_KEY,
            "form": "not available",
            "target_metric_name": "current_assets",
            "target_primary_statement": "balance_sheet",
            "period_context": "not available",
            "recommendation": "review_required",
            "formula_or_value": "",
            "validated_votes": "0/3",
            "agreeing_models": "",
            "review_reason": "no_eligible_raw_fact_pool",
        }
    ]


def test_milestone25_xbrl_concepts_provided_counts_by_period() -> None:
    experiment = _load_experiment_module()
    snapshot = {
        "metric_coverage_resolution": [
            {
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "coverage_status": "needs_llm_resolution",
            }
        ],
        "formula_proposal_diagnostics": [
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-shared",
                "period_context": "10-K periods: 2024 FY, 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "gemini",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-shared",
                "period_context": "10-K periods: 2024 FY, 2025 FY / instant / USD / 10-K",
                "forms": "10-K",
                "provider_name": "openai",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "annual-2023",
                "period_context": "10-K periods: 2023 FY / instant / USD / 10-K",
                "forms": "10-K",
                "concepts_provided": "us-gaap:LongTermDebtCurrent",
            },
            {
                "target_metric_name": "debt_current",
                "target_primary_statement": "balance_sheet",
                "context_id": "quarterly-shared",
                "period_context": "10-Q periods: 2025 Q1 - 2025 Q2 / instant / USD / 10-Q",
                "forms": "10-Q",
                "concepts_provided": "us-gaap:LongTermDebtCurrent, us-gaap:CommercialPaper",
            },
        ],
    }

    assert experiment._xbrl_concepts_provided_10k_rows(snapshot) == [
        {"Year": "2023", "# of concepts provided": 1},
        {"Year": "2024", "# of concepts provided": 2},
        {"Year": "2025", "# of concepts provided": 2},
    ]
    assert experiment._xbrl_concepts_provided_10q_rows(snapshot) == [
        {"Year": "2025", "Q1": 2, "Q2": 2, "Q3": ""},
    ]


def test_milestone25_experiment_presents_first_time_ingestion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "## 0. Compact Summary" in report
    assert "## 0A. XBRL Concepts Provided By Period" in report
    assert "### # of concepts provided from XBRL - 10-K" in report
    assert "### # of concepts provided from XBRL - 10-Q" in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Semantic Candidates For Missing Targets" not in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    assert "formula_proposals_not_run" in report
    assert "review_required" in report
    assert "not available" in report
    assert "## 4. Selected Concept Pools For Formula Recommendations" not in report
    assert "## 4. Final Recommendations For Missing Targets" not in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "### 10-K" in report
    assert "### 10-Q" in report
    assert "Company in system" in report
    assert "Setup ingestion duration seconds" in report
    assert "Unchanged-company reuse duration seconds" in report
    assert "Update check needed this session" in report
    assert "SEC update check performed" in report
    assert "local data reused; no SEC request made" in report
    assert "New filings ingested this session" in report
    assert "Metric-First Coverage Resolution" not in report
    assert (tmp_path / "experiment.db").exists()
    assert (tmp_path / "exports" / "companies.csv").exists()
    assert (tmp_path / "exports" / "financial_metrics.csv").exists()


def test_milestone25_experiment_reports_missing_sec_user_agent(
    tmp_path: Path,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 1
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "Execution Warning" in report
    assert "SEC_USER_AGENT is required for live SEC experiment runs" in report


def test_milestone25_uses_ticker_specific_default_report_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    monkeypatch.setattr(experiment, "EXPERIMENT_DIR", tmp_path)
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "msft",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report_path = tmp_path / "milestone25_mapping_report_MSFT.md"
    report = report_path.read_text(encoding="utf-8")

    assert exit_code == 1
    _assert_report_generation_output(output, report_path)
    assert report_path.exists()
    assert "SEC_USER_AGENT is required for live SEC experiment runs" in report


def test_milestone25_write_report_flag_preserves_markdown_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--write-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "saved Plan 2.5 target mapping report" in report
    assert "## 0. Compact Summary" in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    assert "Component Evidence Samples" not in report
    assert "Evidence Locations" not in report
    assert "Appendix A: Target-Level XBRL Concept Coverage" not in report
    assert "Provider-Level Formula Diagnostics" not in report
    assert "Phase 2" not in report


def test_milestone25_saves_warning_when_csv_export_is_locked(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    original_export_query = experiment._export_query

    def locked_export(connection, query: str, path: Path) -> None:
        if path.name == "financial_metrics.csv":
            raise PermissionError("locked by another process")
        original_export_query(connection, query, path)

    monkeypatch.setattr(experiment, "_export_query", locked_export)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "CSV export skipped for financial_metrics" in report
    assert "## 0. Compact Summary" in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "Evidence Boundary" not in report


def test_milestone25_full_report_flag_prints_detailed_markdown(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "# Plan 2.5 Target Mapping Report" in report
    assert "## 0. Compact Summary" in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    assert "--full-report kept for CLI compatibility" in report
    assert "Appendix A: Target-Level XBRL Concept Coverage" not in report
    assert "Provider-Level Formula Diagnostics" not in report
    assert "Raw Fact and Unknown Concept Evidence" not in report
    assert "Financial Metric Data Lineage View" not in report


def test_milestone25_markdown_table_keeps_identifier_lists_as_text() -> None:
    experiment = _load_experiment_module()
    raw_fact_ids = ",".join(str(100000000000000000000000000000 + index) for index in range(3))
    context_hash = "1234567890123456789012345678901234567890"

    lines = experiment._markdown_table(
        [
            {
                "matched_raw_fact_ids": raw_fact_ids,
                "formula_context_hash": context_hash,
                "amount": "123456789",
            }
        ]
    )
    table = "\n".join(lines)

    assert raw_fact_ids in table
    assert context_hash in table
    assert "123.46M" in table
    assert experiment._format_presentation_number("9" * 80) == "9" * 80


def test_milestone25_markdown_table_keeps_period_context_as_label() -> None:
    experiment = _load_experiment_module()

    lines = experiment._markdown_table(
        [
            {
                "Metric": "debt_current",
                "Period context": "2025",
                "Period coverage": "active 10-K periods: 2021 FY - 2025 FY",
                "amount": "2025",
            }
        ]
    )
    table = "\n".join(lines)
    cells = [cell.strip() for cell in lines[2].strip("|").split("|")]

    assert "2.03K" in table
    assert cells == [
        "debt_current",
        "2025",
        "active 10-K periods: 2021 FY - 2025 FY",
        "2.03K",
    ]


def test_milestone25_markdown_table_keeps_year_as_literal_period_label() -> None:
    experiment = _load_experiment_module()

    lines = experiment._markdown_table(
        [
            {
                "Year": "2021",
                "# of concepts provided": 134,
            },
            {
                "Year": "2025",
                "# of concepts provided": 128,
            },
        ]
    )
    table = "\n".join(lines)

    assert "2021" in table
    assert "2025" in table
    assert "2.02K" not in table
    assert "2.03K" not in table


def test_milestone25_formula_fact_dimension_detection() -> None:
    experiment = _load_experiment_module()

    assert experiment._formula_fact_has_dimensions("[]") is False
    assert experiment._formula_fact_has_dimensions("") is False
    assert experiment._formula_fact_has_dimensions(
        '[["us-gaap:DebtTypeAxis", "us-gaap:CommercialPaperMember"]]'
    ) is True
    assert experiment._formula_fact_has_dimensions("not-json") is True


def test_milestone25_formula_proposal_targets_collapse_missing_tags_by_metric() -> None:
    experiment = _load_experiment_module()

    targets = experiment._formula_proposal_targets(
        [
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "depreciation_and_amortization",
                "statement_type": "cash_flow_statement",
                "target_xbrl_concept": "us-gaap:DepreciationAndAmortization",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DepreciationAndAmortization",
                "industry_label": "Common Base",
            },
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "depreciation_and_amortization",
                "statement_type": "cash_flow_statement",
                "target_xbrl_concept": "us-gaap:DepreciationDepletionAndAmortization",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DepreciationDepletionAndAmortization",
                "industry_label": "Common Base",
            },
            {
                "status": experiment.STATUS_MISSING_TARGET,
                "internal_metric_name": "debt_current",
                "statement_type": "balance_sheet",
                "target_xbrl_concept": "us-gaap:DebtCurrent",
                "taxonomy": "us-gaap",
                "target_raw_concept": "DebtCurrent",
                "industry_label": "Common Base",
            },
        ],
        target_limit=None,
    )

    assert [target.target_metric_name for target in targets] == [
        "depreciation_and_amortization",
        "debt_current",
    ]
    assert "DepreciationAndAmortization" in targets[0].notes
    assert "DepreciationDepletionAndAmortization" in targets[0].notes


def test_milestone25_report_shows_report_only_debt_recovery_diagnostics(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company_with_debt_components(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "Debt Recovery Formula Catalog" not in report
    assert "Report-Only Debt Recovery Diagnostics" not in report
    assert "Debt Recovery Diagnostic Rows" not in report
    assert "Debt Recovery Component Evidence" not in report
    assert "## 1. Target Metrics Mapping Status" in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    snapshot = experiment._snapshot(tmp_path / "experiment.db", "TEST")
    current = next(
        row
        for row in snapshot["debt_recovery_diagnostics"]
        if row["target_metric_name"] == "debt_current"
    )
    assert current["target_recovery_status"] == "derived_from_components"
    assert current["formula_name"] == "debt_current_components"
    assert current["calculated_value"] == "50"
    assert "current_finance_lease_debt" in current["assumed_zero_components"]
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name = 'debt_current'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0


def test_milestone25_report_shows_report_only_formula_proposals_from_found_targets(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        assert formula_context["target_primary_statement"] == target.statement_type
        assert formula_context["period_context"]["fiscal_year"] == 2025
        component_row = next(
            (row for row in fact_pool if "found_target" in row["mapping_statuses"]),
            fact_pool[0],
        )
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="proposed",
            no_formula=False,
            target_is_zero=False,
            formula_expression=f"{target.target_metric_name} = {component_row['taxonomy']}:{component_row['concept']}",
            components=(
                FormulaProposalComponentResponse(
                    component_name="context component",
                    taxonomy=str(component_row["taxonomy"]),
                    concept=str(component_row["concept"]),
                    operator="+",
                    role="already found target fact reused as component evidence",
                    reason="The component is in the eligible same-period raw fact pool",
                ),
            ),
            confidence=0.8,
            reason="test proposal",
            uncertainty="review required",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")
    snapshot = experiment._snapshot(tmp_path / "experiment.db", "TEST")

    assert exit_code == 0
    _assert_formula_progress_output(output)
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    assert "## 4. Selected Concept Pools For Formula Recommendations" not in report
    assert "Formula / Zero Diagnostics Summary" not in report
    assert "Formula Proposal Run Summary" not in report
    assert "Provider-Level Formula Diagnostics" not in report
    assert "Eligible Formula Proposal Raw Fact Pool" not in report
    formula_section = _report_section(
        report,
        "## 2. Proposed Formulas For Formula Recommendations",
        "## 3. Summary Recommendation",
    )
    assert "### 10-K" in formula_section
    assert "### 10-Q" in formula_section
    assert "Formula" in formula_section
    assert "accounts_receivable = Revenues" in formula_section
    assert "all active" not in formula_section
    assert "us-gaap:" not in formula_section
    assert "custom:" not in formula_section
    assert "Recommendation" not in formula_section
    assert "Target concept" not in formula_section
    assert "Components" not in formula_section
    assert "/ duration / USD / 10-K" not in formula_section
    assert "/ instant / USD / 10-K" not in formula_section
    assert "/ instant / USD / 10-Q" not in formula_section
    assert "found_target" not in report
    assert "validated_component_pool" in report
    assert "period-scoped formula contexts" not in report
    assert "Metric-First Coverage Resolution" not in report
    assert "cap_per_target" not in report
    assert "generated_new" not in report
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name <> 'revenue'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0
    assert snapshot["formula_proposal_summary"][0]["value"] == "not_run"


def test_milestone25_report_shows_report_only_zero_target_proposals(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        component_row = fact_pool[0]
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="target_zero",
            no_formula=False,
            target_is_zero=True,
            formula_expression=f"{target.target_metric_name} = 0",
            components=(
                FormulaProposalComponentResponse(
                    component_name="zero evidence",
                    taxonomy=str(component_row["taxonomy"]),
                    concept=str(component_row["concept"]),
                    operator="+",
                    role="same-period raw fact evidence for zero-target review",
                    reason="The evidence fact is in the eligible same-period raw fact pool.",
                ),
            ),
            confidence=0.6,
            reason="Target may be zero based on supplied same-period evidence.",
            uncertainty="Requires review before treating the missing target as zero.",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_formula_progress_output(output)
    assert "target_zero" not in report
    assert "target_is_zero" not in report
    assert "## 2. Missing Target Replacement Recommendations" not in report
    assert "## 2. Proposed Formulas For Formula Recommendations" in report
    assert "## 3. Summary Recommendation" in report
    formula_section = _report_section(
        report,
        "## 2. Proposed Formulas For Formula Recommendations",
        "## 3. Summary Recommendation",
    )
    assert "zero" in formula_section
    assert "## 4. Final Recommendations For Missing Targets" not in report
    assert "accounts_receivable = 0" in formula_section
    assert "validated_zero_evidence_pool" in report
    assert "review zero evidence" not in report
    assert "Zero-target evidence rows" in report
    with connect_sqlite(tmp_path / "experiment.db") as connection:
        stored_recovered_metrics = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM financial_metrics
            WHERE metric_name <> 'revenue'
            """
        ).fetchone()["count"]
    assert stored_recovered_metrics == 0


def test_milestone25_formula_proposals_reuse_failed_provider_result_within_run(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))

    def fake_provider_configs(settings):
        return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

    original_build_contexts = experiment.build_formula_proposal_contexts

    def duplicate_contexts(*, target, fact_pool):
        contexts = original_build_contexts(target=target, fact_pool=fact_pool)
        return contexts[:1] + contexts[:1]

    provider_calls: list[str] = []

    def fake_generate_formula_proposal(
        *,
        ticker: str,
        cik: str,
        target,
        fact_pool,
        formula_context,
        provider,
    ) -> FormulaProposalProviderResult:
        provider_calls.append(str(formula_context["formula_context_hash"]))
        return FormulaProposalProviderResult(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            target_metric_name=target.target_metric_name,
            target_xbrl_concept=target.target_xbrl_concept,
            provider_status="provider_failed",
            no_formula=True,
            target_is_zero=False,
            formula_expression="",
            components=(),
            confidence=0.0,
            reason="",
            uncertainty="",
            error="test provider failure",
        )

    monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
    monkeypatch.setattr(experiment, "build_formula_proposal_contexts", duplicate_contexts)
    monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--formula-proposal-target-limit",
            "1",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    _assert_formula_progress_output(output)
    assert len(provider_calls) == 1
    assert "Provider Outcomes Without Formula Recommendation" in report
    assert "provider_failed" in report
    assert "test provider failure" in report
    assert "No rows to display." in _report_section(
        report,
        "## 2. Proposed Formulas For Formula Recommendations",
    )


def test_milestone25_formula_proposals_batch_targets_by_statement_group(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    target_rows = _formula_batch_target_rows(experiment)
    progress: list[str] = []
    with connect_sqlite(db_path) as connection:
        company_id = _seed_formula_batch_company(connection)

        def fake_provider_configs(settings):
            return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

        batch_calls: list[tuple[tuple[str, ...], str]] = []
        single_calls: list[str] = []

        def fake_generate_formula_proposal_batch(
            *,
            ticker: str,
            cik: str,
            targets,
            fact_pool,
            formula_context,
            provider,
        ) -> tuple[FormulaProposalProviderResult, ...]:
            batch_calls.append(
                (
                    tuple(target.target_metric_name for target in targets),
                    str(formula_context["target_primary_statement"]),
                )
            )
            assert len({target.statement_type for target in targets}) == 1
            return tuple(
                _formula_provider_result(
                    provider=provider,
                    target=target,
                    component_concept="CashAndCashEquivalentsAtCarryingValue",
                )
                for target in targets
            )

        def fake_generate_formula_proposal(
            *,
            ticker: str,
            cik: str,
            target,
            fact_pool,
            formula_context,
            provider,
        ) -> FormulaProposalProviderResult:
            single_calls.append(target.target_metric_name)
            return _formula_provider_result(
                provider=provider,
                target=target,
                component_concept="Revenues",
            )

        monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
        monkeypatch.setattr(experiment, "generate_formula_proposal_batch", fake_generate_formula_proposal_batch)
        monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)

        snapshot = experiment._formula_proposal_snapshot(
            connection,
            ticker="TEST",
            cik="0000000001",
            company_id=company_id,
            target_raw_fact_coverage=target_rows,
            enabled=True,
            settings=SimpleNamespace(knowledge_storage_dir=tmp_path / "knowledge"),
            target_limit=None,
            progress=progress.append,
        )

    assert batch_calls == [(("current_assets", "current_liabilities"), "balance_sheet")]
    assert single_calls == ["gross_profit"]
    assert "statement-scoped batch context(s)" in "\n".join(progress)
    assert {
        row["target_metric_name"]
        for row in snapshot["diagnostics"]
        if row.get("provider_name")
    } == {"current_assets", "current_liabilities", "gross_profit"}


def test_milestone25_formula_proposals_fallback_to_single_when_batch_unusable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    target_rows = _formula_batch_target_rows(experiment)[:2]
    progress: list[str] = []
    with connect_sqlite(db_path) as connection:
        company_id = _seed_formula_batch_company(connection)

        def fake_provider_configs(settings):
            return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

        single_calls: list[str] = []

        def fake_generate_formula_proposal_batch(**kwargs):
            raise ValueError("missing target in batch response")

        def fake_generate_formula_proposal(
            *,
            ticker: str,
            cik: str,
            target,
            fact_pool,
            formula_context,
            provider,
        ) -> FormulaProposalProviderResult:
            single_calls.append(target.target_metric_name)
            return _formula_provider_result(
                provider=provider,
                target=target,
                component_concept="CashAndCashEquivalentsAtCarryingValue",
            )

        monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
        monkeypatch.setattr(experiment, "generate_formula_proposal_batch", fake_generate_formula_proposal_batch)
        monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)

        snapshot = experiment._formula_proposal_snapshot(
            connection,
            ticker="TEST",
            cik="0000000001",
            company_id=company_id,
            target_raw_fact_coverage=target_rows,
            enabled=True,
            settings=SimpleNamespace(knowledge_storage_dir=tmp_path / "knowledge"),
            target_limit=None,
            progress=progress.append,
        )

    assert single_calls == ["current_assets", "current_liabilities"]
    assert "falling back to single-target calls" in "\n".join(progress)
    assert len([row for row in snapshot["diagnostics"] if row.get("provider_name")]) == 2


def test_milestone25_formula_proposals_exclude_cached_targets_from_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    target_rows = _formula_batch_target_rows(experiment)[:2]
    settings = SimpleNamespace(knowledge_storage_dir=tmp_path / "knowledge")
    with connect_sqlite(db_path) as connection:
        company_id = _seed_formula_batch_company(connection)
        fact_pool = experiment._formula_proposal_fact_pool(
            connection,
            company_id=company_id,
            cik="0000000001",
            target_raw_fact_coverage=target_rows,
        )
        cached_target = experiment._formula_proposal_targets(target_rows, target_limit=None)[0]
        cached_context = experiment.build_formula_proposal_contexts(target=cached_target, fact_pool=fact_pool)[0]
        formula_hash, fingerprint_payload = experiment.formula_context_fingerprint(
            target=cached_target,
            context=cached_context,
            provider_name="fake_provider",
            model_name="fake_model",
        )
        experiment.save_formula_proposal_cache(
            cache_dir=experiment._formula_proposal_cache_dir(settings),
            formula_context_hash=formula_hash,
            fingerprint_payload=fingerprint_payload,
            result=_formula_provider_result(
                provider=SimpleNamespace(provider_name="fake_provider", model_name="fake_model"),
                target=cached_target,
                component_concept="CashAndCashEquivalentsAtCarryingValue",
            ),
        )

        def fake_provider_configs(settings):
            return (SimpleNamespace(provider_name="fake_provider", model_name="fake_model", api_key="test"),)

        batch_calls: list[tuple[str, ...]] = []
        single_calls: list[str] = []

        def fake_generate_formula_proposal_batch(*, targets, **kwargs):
            batch_calls.append(tuple(target.target_metric_name for target in targets))
            return ()

        def fake_generate_formula_proposal(
            *,
            ticker: str,
            cik: str,
            target,
            fact_pool,
            formula_context,
            provider,
        ) -> FormulaProposalProviderResult:
            single_calls.append(target.target_metric_name)
            return _formula_provider_result(
                provider=provider,
                target=target,
                component_concept="CashAndCashEquivalentsAtCarryingValue",
            )

        monkeypatch.setattr(experiment, "_formula_proposal_provider_configs", fake_provider_configs)
        monkeypatch.setattr(experiment, "generate_formula_proposal_batch", fake_generate_formula_proposal_batch)
        monkeypatch.setattr(experiment, "generate_formula_proposal", fake_generate_formula_proposal)

        snapshot = experiment._formula_proposal_snapshot(
            connection,
            ticker="TEST",
            cik="0000000001",
            company_id=company_id,
            target_raw_fact_coverage=target_rows,
            enabled=True,
            settings=settings,
            target_limit=None,
            progress=None,
        )

    assert batch_calls == []
    assert single_calls == ["current_liabilities"]
    rows_by_metric = {
        row["target_metric_name"]: row
        for row in snapshot["diagnostics"]
        if row.get("provider_name")
    }
    assert rows_by_metric["current_assets"]["cache_status"] == "reused_exact_context"
    assert rows_by_metric["current_liabilities"]["cache_status"] == "generated_new"


def test_milestone25_formula_progress_distinguishes_cached_provider_from_live_batches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    target_rows = _formula_batch_target_rows(experiment)[:2]
    settings = SimpleNamespace(knowledge_storage_dir=tmp_path / "knowledge")
    progress: list[str] = []
    cached_provider = SimpleNamespace(
        provider_name="fake_provider",
        model_name="cached_model",
        api_key="test",
    )
    live_provider = SimpleNamespace(
        provider_name="fake_provider",
        model_name="live_model",
        api_key="test",
    )

    with connect_sqlite(db_path) as connection:
        company_id = _seed_formula_batch_company(connection)
        fact_pool = experiment._formula_proposal_fact_pool(
            connection,
            company_id=company_id,
            cik="0000000001",
            target_raw_fact_coverage=target_rows,
        )
        targets = experiment._formula_proposal_targets(target_rows, target_limit=None)
        for target in targets:
            context = experiment.build_formula_proposal_contexts(
                target=target,
                fact_pool=fact_pool,
            )[0]
            formula_hash, fingerprint_payload = experiment.formula_context_fingerprint(
                target=target,
                context=context,
                provider_name=cached_provider.provider_name,
                model_name=cached_provider.model_name,
            )
            experiment.save_formula_proposal_cache(
                cache_dir=experiment._formula_proposal_cache_dir(settings),
                formula_context_hash=formula_hash,
                fingerprint_payload=fingerprint_payload,
                result=_formula_provider_result(
                    provider=cached_provider,
                    target=target,
                    component_concept="CashAndCashEquivalentsAtCarryingValue",
                ),
            )

        monkeypatch.setattr(
            experiment,
            "_formula_proposal_provider_configs",
            lambda settings: (cached_provider, live_provider),
        )

        def fake_generate_formula_proposal_batch(*, targets, provider, **kwargs):
            return tuple(
                _formula_provider_result(
                    provider=provider,
                    target=target,
                    component_concept="CashAndCashEquivalentsAtCarryingValue",
                )
                for target in targets
            )

        monkeypatch.setattr(
            experiment,
            "generate_formula_proposal_batch",
            fake_generate_formula_proposal_batch,
        )

        experiment._formula_proposal_snapshot(
            connection,
            ticker="TEST",
            cik="0000000001",
            company_id=company_id,
            target_raw_fact_coverage=target_rows,
            enabled=True,
            settings=settings,
            target_limit=None,
            progress=progress.append,
        )

    output = "\n".join(progress)
    assert (
        "Formula proposal workload: 4 model outcome(s); "
        "2 provider-context batch slot(s): 1 resolved without a live call, "
        "1 live batch request(s)."
    ) in output
    assert (
        "Provider workload fake_provider/cached_model: 2 model outcome(s); "
        "2 reused before live calls; 0 to generate across 0 live batch request(s)."
    ) in output
    assert (
        "Provider workload fake_provider/live_model: 2 model outcome(s); "
        "0 reused before live calls; 2 to generate across 1 live batch request(s)."
    ) in output
    assert "Live batch request 1/1:" in output
    assert "Batch context 1/1:" not in output


def test_milestone25_formula_proposal_fact_pool_uses_active_filing_periods_only(
    tmp_path: Path,
) -> None:
    experiment = _load_experiment_module()
    db_path = tmp_path / "experiment.db"
    with connect_sqlite(db_path) as connection:
        raw_repository = RawFactRepository(connection)
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        raw_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(
                cik="0000000001",
                name="Test Company",
                ticker="TEST",
            )
        )
        assert company.company_id is not None
        filing_repository.upsert_filings(
            company.company_id,
            [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="active-10k",
                    form_type="10-K",
                    filing_date=date(2025, 2, 15),
                    fiscal_year=2025,
                    fiscal_period="FY",
                    is_active_window=True,
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="inactive-10k",
                    form_type="10-K",
                    filing_date=date(2020, 2, 15),
                    fiscal_year=2020,
                    fiscal_period="FY",
                    is_active_window=False,
                ),
            ],
        )
        raw_repository.upsert_facts(
            [
                _fact(
                    form="10-K",
                    accession_number="active-10k",
                    concept="ActiveCurrentPeriodConcept",
                    fiscal_year=2025,
                    fiscal_period="FY",
                ),
                _fact(
                    form="10-K",
                    accession_number="active-10k",
                    concept="ActiveFilingComparativeConcept",
                    fiscal_year=2024,
                    fiscal_period="FY",
                ),
                _fact(
                    form="10-K",
                    accession_number="inactive-10k",
                    concept="InactiveHistoricalConcept",
                    fiscal_year=2020,
                    fiscal_period="FY",
                ),
            ]
        )

        fact_pool = experiment._formula_proposal_fact_pool(
            connection,
            company_id=company.company_id,
            cik="0000000001",
            target_raw_fact_coverage=[],
        )

    assert [fact.concept for fact in fact_pool] == ["ActiveCurrentPeriodConcept"]


def test_milestone25_report_presents_new_filings_when_sec_update_ingests_them(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company_with_update(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--no-formula-proposals",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    _assert_report_generation_output(output, tmp_path / "experiment_report.md")
    assert "Company in system" in report
    assert "Update check needed this session" in report
    assert "SEC update check performed" in report
    assert "SEC checked; new active-window filing data ingested" in report
    assert "New filings ingested this session" in report
    assert "10-Q accession test-10q-new" in report


def _seed_formula_batch_company(connection) -> int:
    initialize_database(connection)
    raw_repository = RawFactRepository(connection)
    company_repository = CompanyRepository(connection)
    filing_repository = FilingRepository(connection)
    raw_repository.initialize()
    company = company_repository.upsert_company(
        CompanyRecord(
            cik="0000000001",
            name="Test Company",
            ticker="TEST",
        )
    )
    assert company.company_id is not None
    filing_repository.upsert_filings(
        company.company_id,
        [
            FilingRecord(
                company_id=company.company_id,
                accession_number="batch-10k",
                form_type="10-K",
                filing_date=date(2025, 2, 15),
                fiscal_year=2025,
                fiscal_period="FY",
                is_active_window=True,
            ),
        ],
    )
    raw_repository.upsert_facts(
        [
            _fact(
                form="10-K",
                accession_number="batch-10k",
                concept="CashAndCashEquivalentsAtCarryingValue",
                label="Cash and cash equivalents",
                period_type="instant",
                start_date=None,
                end_date=date(2025, 12, 31),
            ),
            _fact(
                form="10-K",
                accession_number="batch-10k",
                concept="AccountsReceivableNetCurrent",
                label="Accounts receivable",
                period_type="instant",
                start_date=None,
                end_date=date(2025, 12, 31),
            ),
            _fact(
                form="10-K",
                accession_number="batch-10k",
                concept="Revenues",
                label="Revenue",
                period_type="duration",
            ),
            _fact(
                form="10-K",
                accession_number="batch-10k",
                concept="CostOfRevenue",
                label="Cost of revenue",
                period_type="duration",
            ),
        ]
    )
    return company.company_id


def _formula_batch_target_rows(experiment) -> list[dict[str, str]]:
    return [
        {
            "status": experiment.STATUS_MISSING_TARGET,
            "internal_metric_name": "current_assets",
            "statement_type": "balance_sheet",
            "target_xbrl_concept": "us-gaap:AssetsCurrent",
            "taxonomy": "us-gaap",
            "target_raw_concept": "AssetsCurrent",
            "industry_label": "Common Base",
        },
        {
            "status": experiment.STATUS_MISSING_TARGET,
            "internal_metric_name": "current_liabilities",
            "statement_type": "balance_sheet",
            "target_xbrl_concept": "us-gaap:LiabilitiesCurrent",
            "taxonomy": "us-gaap",
            "target_raw_concept": "LiabilitiesCurrent",
            "industry_label": "Common Base",
        },
        {
            "status": experiment.STATUS_MISSING_TARGET,
            "internal_metric_name": "gross_profit",
            "statement_type": "income_statement",
            "target_xbrl_concept": "us-gaap:GrossProfit",
            "taxonomy": "us-gaap",
            "target_raw_concept": "GrossProfit",
            "industry_label": "Common Base",
        },
    ]


def _summary_target() -> FormulaProposalTarget:
    return FormulaProposalTarget(
        target_metric_name="debt_current",
        target_xbrl_concept="us-gaap:DebtCurrent",
        taxonomy="us-gaap",
        concept="DebtCurrent",
        statement_type="balance_sheet",
    )


def _summary_context() -> FormulaProposalContext:
    return FormulaProposalContext(
        context_id="summary-context",
        target_primary_statement="balance_sheet",
        period_context={
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "period_type": "instant",
            "unit": "USD",
            "forms": ("10-K",),
        },
        facts=(),
        prompt_fact_pool=(),
        statement_relationship_by_key={},
        base_fingerprint_payload={},
    )


def _summary_proposal(
    model_name: str,
    concept: str,
    *,
    target_zero: bool = False,
    failed: bool = False,
    unavailable: bool = False,
) -> FormulaProposalProviderResult:
    if unavailable:
        provider_status = "provider_unavailable"
    elif failed:
        provider_status = "provider_failed"
    elif target_zero:
        provider_status = "target_zero"
    else:
        provider_status = "proposed"
    components = (
        FormulaProposalComponentResponse(
            component_name=concept,
            taxonomy="us-gaap",
            concept=concept,
            operator="+",
            role="test evidence",
            reason="test evidence",
        ),
    ) if concept else ()
    return FormulaProposalProviderResult(
        provider_name="openai" if model_name.startswith("gpt") else "gemini",
        model_name=model_name,
        target_metric_name="debt_current",
        target_xbrl_concept="us-gaap:DebtCurrent",
        provider_status=provider_status,
        no_formula=failed,
        target_is_zero=target_zero,
        formula_expression="debt_current = 0" if target_zero else f"debt_current = us-gaap:{concept}",
        components=components,
        confidence=0.8,
        reason="test proposal",
        uncertainty="review required",
        error="test provider unavailable" if unavailable else "test provider failure" if failed else "",
    )


def _summary_validation(status: str) -> FormulaProposalValidationResult:
    return FormulaProposalValidationResult(
        validation_status=status,
        skip_reason="" if status != VALIDATION_STATUS_FAILED else "test_validation_failure",
        valid_component_count=(
            1
            if status in {VALIDATION_STATUS_VALIDATED, VALIDATION_STATUS_ZERO_EVIDENCE}
            else 0
        ),
    )


def _formula_provider_result(
    *,
    provider,
    target,
    component_concept: str,
) -> FormulaProposalProviderResult:
    return FormulaProposalProviderResult(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        target_metric_name=target.target_metric_name,
        target_xbrl_concept=target.target_xbrl_concept,
        provider_status="proposed",
        no_formula=False,
        target_is_zero=False,
        formula_expression=f"{target.target_metric_name} = us-gaap:{component_concept}",
        components=(
            FormulaProposalComponentResponse(
                component_name=component_concept,
                taxonomy="us-gaap",
                concept=component_concept,
                operator="+",
                role="same statement component",
                reason="The component is in the eligible same-period raw fact pool.",
            ),
        ),
        confidence=0.8,
        reason="test proposal",
        uncertainty="review required",
    )


def _fake_ingest_company(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filing_repository.upsert_filings(
                company.company_id,
                [
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10k",
                        form_type="10-K",
                        filing_date=date(2025, 2, 15),
                        fiscal_year=2025,
                        fiscal_period="FY",
                        local_path=settings.stock_filings_base_dir / "test-10k.htm",
                    ),
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q",
                        form_type="10-Q",
                        filing_date=date(2025, 5, 15),
                        fiscal_year=2025,
                        fiscal_period="Q1",
                        local_path=settings.stock_filings_base_dir / "test-10q.htm",
                    ),
                ],
            )
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "reused_local",
            sec_checked=call_number == 1,
            refresh_due_10k=False,
            refresh_due_10q=False,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10k",
                    form="10-K",
                    filing_date="2025-02-15",
                    primary_document="test-10k.htm",
                    document_url="https://example.test/test-10k.htm",
                ),
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q",
                    form="10-Q",
                    filing_date="2025-05-15",
                    primary_document="test-10q.htm",
                    document_url="https://example.test/test-10q.htm",
                ),
            ),
        )

    return ingest


def _fake_ingest_company_with_mapping_evidence(calls: list[str]):
    base_ingest = _fake_ingest_company(calls)

    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        result = base_ingest(ticker, settings)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            raw_repository.initialize()
            raw_repository.upsert_facts(
                [
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        taxonomy="custom",
                        concept="CustomUnmappedDisclosure",
                        label="Custom unmapped disclosure",
                    ),
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        taxonomy="custom",
                        concept="CustomerAccountsReceivable",
                        label="Customer accounts receivable",
                        period_type="instant",
                    ),
                    _fact(
                        form="10-Q",
                        accession_number="test-10q",
                        taxonomy="custom",
                        concept="CustomerAccountsReceivable",
                        label="Customer accounts receivable",
                        period_type="instant",
                        fiscal_period="Q1",
                        start_date=None,
                        end_date=date(2025, 3, 31),
                        filed_date=date(2025, 5, 15),
                    )
                ]
            )
            repository = ConceptMappingRepository(connection)
            repository.initialize()
            repository.upsert_mappings(
                (
                    ConceptMappingRecord(
                        taxonomy="custom",
                        concept="CustomerRevenueApproved",
                        metric_name="revenue",
                        statement_type="income_statement",
                        scope_type=MAPPING_SCOPE_COMPANY,
                        scope_value="0000000001",
                        status=MAPPING_STATUS_APPROVED,
                        confidence=0.99,
                        match_method="manual_review",
                        evidence={"reason": "approved company concept profile test"},
                        reviewed_by="tester",
                        reviewed_at="2026-01-01T00:00:00+00:00",
                    ),
                )
            )
        return result

    return ingest


def _fake_ingest_company_with_debt_components(calls: list[str]):
    base_ingest = _fake_ingest_company(calls)

    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        result = base_ingest(ticker, settings)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            company = company_repository.get_by_ticker(ticker)
            assert company is not None
            assert company.company_id is not None
            raw_repository.upsert_facts(
                [
                    _fact(
                        form="10-K",
                        accession_number="test-10k",
                        concept="LongTermDebtCurrent",
                        label="Long-term debt current",
                    )
                ]
            )
            raw_fact_by_concept = {
                record.fact.concept: record.raw_fact_id
                for record in raw_repository.list_fact_records("0000000001")
            }
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact_by_concept["LongTermDebtCurrent"],
                        statement_type="balance_sheet",
                        metric_name="long_term_debt_current",
                        value_numeric=Decimal("50"),
                        value_raw=50,
                        unit="USD",
                        period_type="instant",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        end_date=date(2025, 12, 31),
                        filing_date=date(2026, 2, 1),
                    )
                ]
            )
        return result

    return ingest


def _fake_ingest_company_with_update(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 8, 15) if call_number == 2 else date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1) if call_number == 2 else date(2020, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filings = [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10k",
                    form_type="10-K",
                    filing_date=date(2025, 2, 15),
                    fiscal_year=2025,
                    fiscal_period="FY",
                    local_path=settings.stock_filings_base_dir / "test-10k.htm",
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10q",
                    form_type="10-Q",
                    filing_date=date(2025, 5, 15),
                    fiscal_year=2025,
                    fiscal_period="Q1",
                    local_path=settings.stock_filings_base_dir / "test-10q.htm",
                ),
            ]
            if call_number == 2:
                filings.append(
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q-new",
                        form_type="10-Q",
                        filing_date=date(2025, 8, 15),
                        fiscal_year=2025,
                        fiscal_period="Q2",
                        local_path=settings.stock_filings_base_dir / "test-10q-new.htm",
                    )
                )
            filing_repository.upsert_filings(company.company_id, filings)
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "updated",
            sec_checked=True,
            refresh_due_10k=False,
            refresh_due_10q=call_number == 2,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q-new" if call_number == 2 else "test-10q",
                    form="10-Q",
                    filing_date="2025-08-15" if call_number == 2 else "2025-05-15",
                    primary_document="test-10q-new.htm" if call_number == 2 else "test-10q.htm",
                    document_url="https://example.test/test-10q-new.htm",
                ),
            ),
        )

    return ingest


def _fact(
    *,
    form: str,
    accession_number: str,
    taxonomy: str = "us-gaap",
    concept: str = "Revenues",
    label: str = "Revenues",
    period_type: str = "duration",
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    start_date: date | None = date(2024, 1, 1),
    end_date: date | None = date(2024, 12, 31),
    filed_date: date | None = date(2025, 2, 15),
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Test Company",
        taxonomy=taxonomy,
        concept=concept,
        label=label,
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=start_date,
        end_date=end_date,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=filed_date,
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )


def _env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        f"SEC_USER_AGENT=Test contact@example.com\nKNOWLEDGE_STORAGE_DIR={tmp_path / 'knowledge'}\n",
        encoding="utf-8",
    )
    return env_file
