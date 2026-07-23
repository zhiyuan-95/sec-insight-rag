import pytest

from src.processing.company_industry_labels import (
    LABEL_STATUS_ASSIGNED,
    LABEL_STATUS_NEEDS_REVIEW,
    industry_label_assignments_for_company,
    validate_industry_labels,
)
from src.processing.mapping_catalog import (
    COMMON_BASE_LABEL,
    mapping_candidates_by_concept,
    target_facts_for_industry_labels,
)


def test_known_company_labels_are_resolved_by_normalized_ticker_and_cik() -> None:
    by_ticker = industry_label_assignments_for_company(" msft ", None)
    by_cik = industry_label_assignments_for_company(None, "789019")

    assert by_ticker == by_cik
    assert by_ticker.label_status == LABEL_STATUS_ASSIGNED
    assert by_ticker.assigned_industry_labels == (
        "Information Technology",
        "Communication Services",
    )


def test_unknown_company_returns_review_placeholder_with_supporting_evidence() -> None:
    assignment = industry_label_assignments_for_company(
        "new",
        "123",
        sic="9999",
        sic_description="Example industry",
        observed_concepts=("ZetaConcept", "AlphaConcept", "AlphaConcept"),
    )

    assert assignment.ticker == "NEW"
    assert assignment.cik == "0000000123"
    assert assignment.label_status == LABEL_STATUS_NEEDS_REVIEW
    assert assignment.assigned_industry_labels == ()
    assert assignment.supporting_evidence == (
        "SEC SIC: 9999",
        "SEC SIC description: Example industry",
        "Observed XBRL concept sample for review only: AlphaConcept, ZetaConcept",
    )


def test_validate_industry_labels_deduplicates_and_rejects_unknown_values() -> None:
    assert validate_industry_labels(
        ("Energy", " Energy ", "Materials")
    ) == ("Energy", "Materials")

    with pytest.raises(ValueError, match="Unknown hard industry labels: Banking"):
        validate_industry_labels(("Banking",))


def test_industry_targets_extend_common_targets_without_duplicate_mappings() -> None:
    targets = target_facts_for_industry_labels(("Energy",))
    mapping_keys = {
        (target.taxonomy, target.raw_concept, target.internal_metric_name, target.statement_type)
        for target in targets
    }

    assert len(mapping_keys) == len(targets)
    assert any(target.industry_label == COMMON_BASE_LABEL for target in targets)
    assert any("Energy" in target.industry_label for target in targets)


def test_multiple_period_labels_produce_one_deduplicated_target_union() -> None:
    targets = target_facts_for_industry_labels(("Energy", "Materials"))
    mapping_keys = {
        (
            target.taxonomy,
            target.raw_concept,
            target.internal_metric_name,
            target.statement_type,
        )
        for target in targets
    }
    expected_keys = {
        (
            target.taxonomy,
            target.raw_concept,
            target.internal_metric_name,
            target.statement_type,
        )
        for label in ("Energy", "Materials")
        for target in target_facts_for_industry_labels((label,))
    }

    assert len(mapping_keys) == len(targets)
    assert mapping_keys == expected_keys


def test_period_without_labels_uses_common_base_targets_only() -> None:
    targets = target_facts_for_industry_labels(())

    assert targets
    assert {target.industry_label for target in targets} == {
        COMMON_BASE_LABEL
    }


def test_mapping_candidates_prefer_common_mapping_for_shared_concepts() -> None:
    candidates = mapping_candidates_by_concept(("Energy",))

    assert candidates["Revenues"].internal_metric_name == "revenue"
    assert candidates["Revenues"].industry_label == COMMON_BASE_LABEL
    assert "AssetRetirementObligation" in candidates


def test_direct_standard_candidates_from_mapping_file_are_available() -> None:
    common_candidates = mapping_candidates_by_concept(())

    assert (
        common_candidates["RevenueFromContractWithCustomerIncludingAssessedTax"].internal_metric_name
        == "revenue"
    )
    assert common_candidates["ProfitLoss"].internal_metric_name == "net_income"
    assert common_candidates["InterestAndDebtExpense"].internal_metric_name == "interest_expense"
    assert common_candidates["InterestExpenseNonoperating"].internal_metric_name == "interest_expense"
    assert common_candidates["MarketableSecuritiesCurrent"].internal_metric_name == "short_term_investments"
    assert common_candidates["AvailableForSaleSecuritiesCurrent"].internal_metric_name == "short_term_investments"
    assert common_candidates["TradingSecuritiesCurrent"].internal_metric_name == "short_term_investments"
    assert common_candidates["HeldToMaturitySecuritiesCurrent"].internal_metric_name == "short_term_investments"
    assert common_candidates["OtherShortTermInvestments"].internal_metric_name == "short_term_investments"
    assert common_candidates["InvestmentsCurrent"].internal_metric_name == "short_term_investments"
    assert common_candidates["FinanceLeaseLiabilityCurrent"].internal_metric_name == "finance_lease_liability_current"
    assert common_candidates["FinanceLeaseLiabilityNoncurrent"].internal_metric_name == "finance_lease_liability_noncurrent"
    assert common_candidates["DepreciationAndAmortization"].internal_metric_name == "depreciation_and_amortization"
    assert (
        common_candidates["DepreciationAmortizationAndAccretionNet"].internal_metric_name
        == "depreciation_and_amortization"
    )
    assert common_candidates["Depreciation"].internal_metric_name == "depreciation"
    assert (
        common_candidates["AmortizationOfIntangibleAssets"].internal_metric_name
        == "amortization_of_intangible_assets"
    )
    assert (
        common_candidates["WeightedAverageNumberOfSharesOutstandingBasicAndDiluted"].internal_metric_name
        == "weighted_average_diluted_shares"
    )
    assert common_candidates["AccountsPayableTradeCurrent"].internal_metric_name == "accounts_payable"
    assert common_candidates["PaymentsToAcquireProductiveAssets"].internal_metric_name == "capital_expenditure"


def test_direct_standard_candidates_stay_scoped_to_selected_industry_labels() -> None:
    common_candidates = mapping_candidates_by_concept(())
    energy_candidates = mapping_candidates_by_concept(("Energy",))
    communication_candidates = mapping_candidates_by_concept(("Communication Services",))
    real_estate_candidates = mapping_candidates_by_concept(("Real Estate",))

    assert "AssetRetirementObligations" not in common_candidates
    assert energy_candidates["AssetRetirementObligations"].internal_metric_name == "asset_retirement_obligation"
    assert communication_candidates["DeferredRevenueNoncurrent"].internal_metric_name == "deferred_revenue_noncurrent"
    assert (
        real_estate_candidates["OperatingLeasesIncomeStatementLeaseRevenue"].internal_metric_name
        == "operating_lease_income"
    )


def test_short_term_investments_are_common_target_facts_for_indicators() -> None:
    targets = target_facts_for_industry_labels(())
    short_term_investment_concepts = {
        target.raw_concept
        for target in targets
        if target.internal_metric_name == "short_term_investments"
    }

    assert short_term_investment_concepts == {
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent",
        "TradingSecuritiesCurrent",
        "HeldToMaturitySecuritiesCurrent",
        "OtherShortTermInvestments",
        "InvestmentsCurrent",
    }


def test_company_extension_wildcards_are_not_hard_mapping_candidates() -> None:
    candidates = mapping_candidates_by_concept()

    assert not any("*" in concept for concept in candidates)
