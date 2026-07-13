from src.processing.mapping_catalog import (
    STATUS_FOUND_MAPPED,
    STATUS_FOUND_MAPPED_ALTERNATE,
    STATUS_MISSING_TARGET,
)
from src.processing.metric_coverage import (
    METRIC_COVERAGE_APPROVED_ALTERNATE,
    METRIC_COVERAGE_MAPPED,
    METRIC_COVERAGE_NEEDS_LLM_RESOLUTION,
    METRIC_COVERAGE_NO_EVIDENCE,
    RESOLUTION_OPTION_FORMULA,
    RESOLUTION_OPTION_SEMANTIC,
    RESOLUTION_OPTION_ZERO,
    metric_coverage_report_rows,
    resolve_metric_coverage,
)


def test_resolve_metric_coverage_prefers_existing_mapping() -> None:
    resolutions = resolve_metric_coverage(
        target_coverage_rows=[
            _target("revenue", "us-gaap:Revenue", STATUS_FOUND_MAPPED),
            _target(
                "revenue",
                "us-gaap:SalesRevenueNet",
                STATUS_FOUND_MAPPED_ALTERNATE,
                alternate_mapped_concepts="us-gaap:Revenue",
            ),
        ],
        semantic_candidate_rows=[
            _semantic_candidate("revenue", "custom:CustomerRevenue")
        ],
    )

    assert len(resolutions) == 1
    resolution = resolutions[0]
    assert resolution.coverage_status == METRIC_COVERAGE_MAPPED
    assert resolution.reviewer_action == "none"
    assert resolution.llm_choice_options == ()


def test_resolve_metric_coverage_tracks_approved_alternate() -> None:
    resolutions = resolve_metric_coverage(
        target_coverage_rows=[
            _target(
                "net_income",
                "us-gaap:ProfitLoss",
                STATUS_FOUND_MAPPED_ALTERNATE,
                alternate_mapped_concepts="us-gaap:NetIncomeLoss",
            )
        ]
    )

    resolution = resolutions[0]
    assert resolution.coverage_status == METRIC_COVERAGE_APPROVED_ALTERNATE
    assert resolution.approved_alternate_concepts == ("us-gaap:NetIncomeLoss",)
    assert resolution.llm_choice_options == ()


def test_resolve_metric_coverage_exposes_llm_choice_options() -> None:
    resolutions = resolve_metric_coverage(
        target_coverage_rows=[
            _target("debt_current", "us-gaap:DebtCurrent", STATUS_MISSING_TARGET)
        ],
        semantic_candidate_rows=[
            _semantic_candidate("debt_current", "custom:CurrentDebtEquivalent")
        ],
        formula_diagnostic_rows=[
            _formula_row(
                "debt_current",
                provider_status="proposed",
                validation_status="validated_component_pool",
            ),
            _formula_row(
                "debt_current",
                provider_status="target_zero",
                validation_status="validated_zero_evidence_pool",
            ),
        ],
    )

    resolution = resolutions[0]
    assert resolution.coverage_status == METRIC_COVERAGE_NEEDS_LLM_RESOLUTION
    assert resolution.llm_choice_options == (
        RESOLUTION_OPTION_SEMANTIC,
        RESOLUTION_OPTION_FORMULA,
        RESOLUTION_OPTION_ZERO,
    )
    rows = metric_coverage_report_rows(resolutions)
    assert rows[0]["reviewer_action"] == "llm_choose_mapping_formula_or_zero"
    assert rows[0]["semantic_candidates"] == "custom:CurrentDebtEquivalent"
    assert rows[0]["formula_evidence"] == "proposed=1; validated=1; no_formula=0"
    assert rows[0]["zero_evidence"] == "proposed=1; validated=1"


def test_resolve_metric_coverage_marks_no_evidence() -> None:
    resolutions = resolve_metric_coverage(
        target_coverage_rows=[
            _target(
                "operating_lease_liability_current",
                "us-gaap:OperatingLeaseLiabilityCurrent",
                STATUS_MISSING_TARGET,
            )
        ],
    )

    resolution = resolutions[0]
    assert resolution.coverage_status == METRIC_COVERAGE_NO_EVIDENCE
    assert resolution.reviewer_action == "no_evidence_to_review"
    assert resolution.llm_choice_options == ()


def _target(
    metric_name: str,
    target_xbrl_concept: str,
    status: str,
    *,
    statement_type: str = "balance_sheet",
    alternate_mapped_concepts: str = "",
) -> dict[str, object]:
    taxonomy, concept = target_xbrl_concept.split(":", 1)
    return {
        "internal_metric_name": metric_name,
        "statement_type": statement_type,
        "target_xbrl_concept": target_xbrl_concept,
        "taxonomy": taxonomy,
        "target_raw_concept": concept,
        "status": status,
        "alternate_mapped_concepts": alternate_mapped_concepts,
    }


def _semantic_candidate(
    metric_name: str,
    observed_xbrl_concept: str,
    *,
    statement_type: str = "balance_sheet",
) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "statement_type": statement_type,
        "observed_xbrl_concept": observed_xbrl_concept,
    }


def _formula_row(
    metric_name: str,
    *,
    provider_status: str,
    validation_status: str,
    statement_type: str = "balance_sheet",
) -> dict[str, object]:
    return {
        "target_metric_name": metric_name,
        "target_primary_statement": statement_type,
        "provider_status": provider_status,
        "validation_status": validation_status,
    }
