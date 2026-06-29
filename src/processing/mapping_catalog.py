"""Inspectable hard-industry-label target fact and mapping catalog."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.processing.company_industry_labels import HARD_INDUSTRY_LABELS, validate_industry_labels

COMMON_BASE_LABEL = "Common Base"

STATUS_FOUND_MAPPED = "found_mapped"
STATUS_FOUND_UNMAPPED = "found_unmapped"
STATUS_MISSING_TARGET = "missing_target"


@dataclass(frozen=True)
class IndustryLabelDefinition:
    """Human-readable definition for a hard industry label."""

    industry_label: str
    description: str
    assignment_notes: str
    notes: str = ""


@dataclass(frozen=True)
class IndustryFactTarget:
    """A raw SEC/XBRL concept intentionally tracked by the mapping catalog."""

    industry_label: str
    raw_concept: str
    taxonomy: str
    internal_metric_name: str
    statement_type: str
    required_for_core: bool
    required_for_specialized_indicators: bool
    consolidated_or_segment: str
    priority: int
    notes: str = ""

    @property
    def metric_name(self) -> str:
        """Compatibility alias used by the existing base metric mapper."""
        return self.internal_metric_name


@dataclass(frozen=True)
class MappingDecision:
    """A reviewed mapping decision for one raw concept."""

    raw_concept: str
    internal_metric_name: str
    status: str
    reason: str


def _target(
    industry_label: str,
    raw_concept: str,
    internal_metric_name: str,
    statement_type: str,
    *,
    taxonomy: str = "us-gaap",
    required_for_core: bool = True,
    required_for_specialized_indicators: bool = False,
    consolidated_or_segment: str = "consolidated",
    priority: int = 10,
    notes: str = "",
) -> IndustryFactTarget:
    return IndustryFactTarget(
        industry_label=industry_label,
        raw_concept=raw_concept,
        taxonomy=taxonomy,
        internal_metric_name=internal_metric_name,
        statement_type=statement_type,
        required_for_core=required_for_core,
        required_for_specialized_indicators=required_for_specialized_indicators,
        consolidated_or_segment=consolidated_or_segment,
        priority=priority,
        notes=notes,
    )


def _industry_target(
    industry_label: str,
    raw_concept: str,
    internal_metric_name: str,
    statement_type: str,
    *,
    priority: int = 100,
    notes: str = "",
) -> IndustryFactTarget:
    return _target(
        industry_label,
        raw_concept,
        internal_metric_name,
        statement_type,
        required_for_core=False,
        required_for_specialized_indicators=True,
        priority=priority,
        notes=notes,
    )


INDUSTRY_LABEL_DEFINITIONS = tuple(
    IndustryLabelDefinition(
        industry_label=label,
        description=f"Hard industry label for {label} companies.",
        assignment_notes=(
            "Assign from the source-controlled company label registry first. "
            "Use SIC, business description, and observed XBRL concepts as supporting evidence."
        ),
    )
    for label in HARD_INDUSTRY_LABELS
)

COMMON_BASE_TARGETS = (
    _target(COMMON_BASE_LABEL, "RevenueFromContractWithCustomerExcludingAssessedTax", "revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "RevenueFromContractWithCustomerIncludingAssessedTax", "revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "Revenues", "revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "SalesRevenueNet", "revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "CostOfRevenue", "cost_of_revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "CostOfGoodsAndServicesSold", "cost_of_revenue", "income_statement"),
    _target(COMMON_BASE_LABEL, "GrossProfit", "gross_profit", "income_statement"),
    _target(COMMON_BASE_LABEL, "OperatingIncomeLoss", "operating_income", "income_statement"),
    _target(
        COMMON_BASE_LABEL,
        "NetIncomeLoss",
        "net_income",
        "income_statement",
        notes="Positive values mean net income/profit; negative values mean net loss.",
    ),
    _target(
        COMMON_BASE_LABEL,
        "ProfitLoss",
        "net_income",
        "income_statement",
        notes="Standard bottom-line profit or loss tag; use as an alternate to NetIncomeLoss when reported.",
    ),
    _target(COMMON_BASE_LABEL, "ResearchAndDevelopmentExpense", "research_and_development_expense", "income_statement"),
    _target(
        COMMON_BASE_LABEL,
        "SellingGeneralAndAdministrativeExpense",
        "selling_general_and_administrative_expense",
        "income_statement",
    ),
    _target(COMMON_BASE_LABEL, "InterestExpenseNonOperating", "interest_expense", "income_statement"),
    _target(COMMON_BASE_LABEL, "InterestExpenseNonoperating", "interest_expense", "income_statement"),
    _target(COMMON_BASE_LABEL, "InterestExpense", "interest_expense", "income_statement"),
    _target(COMMON_BASE_LABEL, "InterestAndDebtExpense", "interest_expense", "income_statement"),
    _target(COMMON_BASE_LABEL, "EarningsPerShareDiluted", "diluted_eps", "income_statement"),
    _target(COMMON_BASE_LABEL, "EarningsPerShareBasicAndDiluted", "diluted_eps", "income_statement"),
    _target(COMMON_BASE_LABEL, "WeightedAverageNumberOfDilutedSharesOutstanding", "weighted_average_diluted_shares", "shares"),
    _target(
        COMMON_BASE_LABEL,
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
        "weighted_average_diluted_shares",
        "shares",
    ),
    _target(COMMON_BASE_LABEL, "CashAndCashEquivalentsAtCarryingValue", "cash_and_equivalents", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "Assets", "total_assets", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "AssetsCurrent", "current_assets", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "Liabilities", "total_liabilities", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "LiabilitiesCurrent", "current_liabilities", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "AccountsReceivableNetCurrent", "accounts_receivable", "balance_sheet"),
    _target(
        COMMON_BASE_LABEL,
        "AccountsNotesAndLoansReceivableNetCurrent",
        "accounts_receivable",
        "balance_sheet",
        notes="Broader current receivables tag; inspect if a trade-only accounts receivable value is required.",
    ),
    _target(COMMON_BASE_LABEL, "AccountsPayableCurrent", "accounts_payable", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "AccountsPayableTradeCurrent", "accounts_payable", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "DebtCurrent", "debt_current", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "DebtNoncurrent", "debt_noncurrent", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "LongTermDebtCurrent", "long_term_debt_current", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "LongTermDebtNoncurrent", "long_term_debt_noncurrent", "balance_sheet"),
    _target(
        COMMON_BASE_LABEL,
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "long_term_debt_and_finance_lease_obligations_current",
        "balance_sheet",
    ),
    _target(
        COMMON_BASE_LABEL,
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "long_term_debt_and_finance_lease_obligations_noncurrent",
        "balance_sheet",
    ),
    _target(COMMON_BASE_LABEL, "FinanceLeaseLiabilityCurrent", "finance_lease_liability_current", "balance_sheet"),
    _target(
        COMMON_BASE_LABEL,
        "FinanceLeaseLiabilityNoncurrent",
        "finance_lease_liability_noncurrent",
        "balance_sheet",
    ),
    _target(COMMON_BASE_LABEL, "ShortTermBorrowings", "short_term_borrowings", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "ShortTermInvestments", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "MarketableSecuritiesCurrent", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "AvailableForSaleSecuritiesCurrent", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "TradingSecuritiesCurrent", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "HeldToMaturitySecuritiesCurrent", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "OtherShortTermInvestments", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "InvestmentsCurrent", "short_term_investments", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "StockholdersEquity", "shareholders_equity", "balance_sheet"),
    _target(COMMON_BASE_LABEL, "NetCashProvidedByUsedInOperatingActivities", "operating_cash_flow", "cash_flow_statement"),
    _target(COMMON_BASE_LABEL, "PaymentsToAcquirePropertyPlantAndEquipment", "capital_expenditure", "cash_flow_statement"),
    _target(
        COMMON_BASE_LABEL,
        "PaymentsToAcquireProductiveAssets",
        "capital_expenditure",
        "cash_flow_statement",
        notes="Broader capital-expenditure tag for productive assets; inspect against PP&E-only capex needs.",
    ),
    _target(COMMON_BASE_LABEL, "DepreciationDepletionAndAmortization", "depreciation_and_amortization", "cash_flow_statement"),
    _target(
        COMMON_BASE_LABEL,
        "DepreciationDepletionAndAmortizationExpense",
        "depreciation_and_amortization",
        "cash_flow_statement",
    ),
    _target(COMMON_BASE_LABEL, "DepreciationAndAmortization", "depreciation_and_amortization", "cash_flow_statement"),
    _target(
        COMMON_BASE_LABEL,
        "DepreciationAmortizationAndAccretionNet",
        "depreciation_and_amortization",
        "cash_flow_statement",
    ),
    _target(COMMON_BASE_LABEL, "Depreciation", "depreciation", "cash_flow_statement"),
    _target(
        COMMON_BASE_LABEL,
        "AmortizationOfIntangibleAssets",
        "amortization_of_intangible_assets",
        "cash_flow_statement",
    ),
)

COMMON_MAPPING_COMPATIBILITY_TARGETS = (
    _target(
        COMMON_BASE_LABEL,
        "InventoryNet",
        "inventory",
        "balance_sheet",
        notes="Approved mapping candidate kept to preserve current Plan 2.5 behavior; target coverage treats inventory as industry-specific.",
    ),
)

INDUSTRY_TARGETS = (
    _industry_target("Energy", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Energy", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Energy", "AssetRetirementObligation", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Energy", "AssetRetirementObligations", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Materials", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Materials", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Materials", "AssetRetirementObligation", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Materials", "AssetRetirementObligations", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Materials", "EnvironmentalRemediationExpense", "environmental_remediation_expense", "income_statement"),
    _industry_target("Industrials", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Industrials", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Industrials", "ContractAssetCurrent", "contract_assets_current", "balance_sheet"),
    _industry_target("Industrials", "ContractWithCustomerAssetCurrent", "contract_assets_current", "balance_sheet"),
    _industry_target("Industrials", "ContractWithCustomerLiabilityCurrent", "contract_liabilities_current", "balance_sheet", priority=80),
    _industry_target("Industrials", "DeferredRevenueCurrent", "contract_liabilities_current", "balance_sheet", priority=90),
    _industry_target("Industrials", "Backlog", "backlog", "operating_metric"),
    _industry_target("Consumer Discretionary", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Consumer Discretionary", "MerchandiseInventory", "inventory", "balance_sheet"),
    _industry_target("Consumer Discretionary", "OperatingLeaseRightOfUseAsset", "operating_lease_right_of_use_asset", "balance_sheet"),
    _industry_target("Consumer Discretionary", "OperatingLeaseLiabilityCurrent", "operating_lease_liability_current", "balance_sheet"),
    _industry_target("Consumer Discretionary", "OperatingLeaseLiabilityNoncurrent", "operating_lease_liability_noncurrent", "balance_sheet"),
    _industry_target("Consumer Discretionary", "AdvertisingExpense", "advertising_expense", "income_statement"),
    _industry_target("Consumer Staples", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Consumer Staples", "MerchandiseInventory", "inventory", "balance_sheet"),
    _industry_target("Consumer Staples", "OperatingLeaseRightOfUseAsset", "operating_lease_right_of_use_asset", "balance_sheet"),
    _industry_target("Consumer Staples", "OperatingLeaseLiabilityCurrent", "operating_lease_liability_current", "balance_sheet"),
    _industry_target("Consumer Staples", "OperatingLeaseLiabilityNoncurrent", "operating_lease_liability_noncurrent", "balance_sheet"),
    _industry_target("Consumer Staples", "AdvertisingExpense", "advertising_expense", "income_statement"),
    _industry_target("Health Care", "InventoryNet", "inventory", "balance_sheet"),
    _industry_target("Health Care", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Health Care", "IntangibleAssetsNetExcludingGoodwill", "intangible_assets", "balance_sheet"),
    _industry_target("Health Care", "Goodwill", "goodwill", "balance_sheet"),
    _industry_target("Financials", "InterestIncomeExpenseNet", "net_interest_income", "income_statement"),
    _industry_target("Financials", "InterestIncomeExpenseNonOperatingNet", "net_interest_income", "income_statement"),
    _industry_target("Financials", "LoansAndLeasesReceivableNetReportedAmount", "loans_receivable", "balance_sheet"),
    _industry_target("Financials", "Deposits", "deposits", "balance_sheet"),
    _industry_target("Financials", "AllowanceForCreditLosses", "allowance_for_credit_losses", "balance_sheet"),
    _industry_target("Financials", "AllowanceForLoanAndLeaseLosses", "allowance_for_credit_losses", "balance_sheet"),
    _industry_target("Financials", "PremiumsEarnedNet", "insurance_premiums", "income_statement"),
    _industry_target("Financials", "InsuranceClaimsAndClaimsExpense", "insurance_claims_expense", "income_statement"),
    _industry_target("Financials", "InvestmentIncomeNet", "investment_income", "income_statement"),
    _industry_target("Information Technology", "ContractWithCustomerLiabilityCurrent", "deferred_revenue_current", "balance_sheet", priority=70),
    _industry_target("Information Technology", "ContractWithCustomerLiabilityNoncurrent", "deferred_revenue_noncurrent", "balance_sheet"),
    _industry_target("Information Technology", "DeferredRevenueCurrent", "deferred_revenue_current", "balance_sheet"),
    _industry_target("Information Technology", "DeferredRevenueNoncurrent", "deferred_revenue_noncurrent", "balance_sheet"),
    _industry_target("Information Technology", "SellingAndMarketingExpense", "selling_and_marketing_expense", "income_statement"),
    _industry_target("Information Technology", "IntangibleAssetsNetExcludingGoodwill", "intangible_assets", "balance_sheet"),
    _industry_target("Information Technology", "Goodwill", "goodwill", "balance_sheet"),
    _industry_target("Communication Services", "ContractWithCustomerLiabilityCurrent", "deferred_revenue_current", "balance_sheet", priority=70),
    _industry_target("Communication Services", "ContractWithCustomerLiabilityNoncurrent", "deferred_revenue_noncurrent", "balance_sheet"),
    _industry_target("Communication Services", "DeferredRevenueCurrent", "deferred_revenue_current", "balance_sheet"),
    _industry_target("Communication Services", "DeferredRevenueNoncurrent", "deferred_revenue_noncurrent", "balance_sheet"),
    _industry_target("Communication Services", "SellingAndMarketingExpense", "selling_and_marketing_expense", "income_statement"),
    _industry_target("Communication Services", "Goodwill", "goodwill", "balance_sheet"),
    _industry_target("Communication Services", "IntangibleAssetsNetExcludingGoodwill", "intangible_assets", "balance_sheet"),
    _industry_target("Utilities", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Utilities", "UtilityPlantNet", "utility_plant", "balance_sheet"),
    _industry_target("Utilities", "RegulatedAndUnregulatedOperatingRevenue", "revenue", "income_statement"),
    _industry_target("Utilities", "AssetRetirementObligation", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Utilities", "AssetRetirementObligations", "asset_retirement_obligation", "balance_sheet"),
    _industry_target("Real Estate", "RentalIncome", "rental_income", "income_statement"),
    _industry_target("Real Estate", "RealEstateInvestmentPropertyNet", "real_estate_investment_property", "balance_sheet"),
    _industry_target("Real Estate", "RealEstateAccumulatedDepreciation", "real_estate_accumulated_depreciation", "balance_sheet"),
    _industry_target("Real Estate", "OperatingLeaseIncome", "operating_lease_income", "income_statement"),
    _industry_target("Real Estate", "OperatingLeasesIncomeStatementLeaseRevenue", "operating_lease_income", "income_statement"),
    _industry_target("Real Estate", "PropertyPlantAndEquipmentNet", "property_plant_and_equipment", "balance_sheet"),
    _industry_target("Real Estate", "MortgageLoansOnRealEstate", "mortgage_loans_on_real_estate", "balance_sheet"),
)


def target_facts_for_industry_labels(
    industry_labels: Iterable[str],
    *,
    include_common: bool = True,
) -> tuple[IndustryFactTarget, ...]:
    """Return common targets plus target facts for the assigned hard labels."""
    labels = set(validate_industry_labels(industry_labels))
    targets: list[IndustryFactTarget] = []
    if include_common:
        targets.extend(COMMON_BASE_TARGETS)
    targets.extend(target for target in INDUSTRY_TARGETS if target.industry_label in labels)
    return _merge_duplicate_targets(targets)


def mapping_candidates_by_concept(
    industry_labels: Iterable[str] | None = None,
) -> dict[str, IndustryFactTarget]:
    """Return the selected mapping candidate for each raw XBRL concept."""
    if industry_labels is None:
        candidates = (*COMMON_BASE_TARGETS, *COMMON_MAPPING_COMPATIBILITY_TARGETS, *INDUSTRY_TARGETS)
    else:
        candidates = (
            *COMMON_BASE_TARGETS,
            *COMMON_MAPPING_COMPATIBILITY_TARGETS,
            *target_facts_for_industry_labels(industry_labels, include_common=False),
        )

    selected: dict[str, IndustryFactTarget] = {}
    for candidate in candidates:
        current = selected.get(candidate.raw_concept)
        if current is None or _mapping_sort_key(candidate) < _mapping_sort_key(current):
            selected[candidate.raw_concept] = candidate
    return dict(sorted(selected.items()))


def mapping_candidates_by_key(
    industry_labels: Iterable[str] | None = None,
) -> dict[tuple[str, str], IndustryFactTarget]:
    """Return mapping candidates keyed by taxonomy and concept."""
    return {
        (target.taxonomy, concept): target
        for concept, target in mapping_candidates_by_concept(industry_labels).items()
    }


def all_target_facts() -> tuple[IndustryFactTarget, ...]:
    """Return every target fact in the catalog."""
    return _merge_duplicate_targets((*COMMON_BASE_TARGETS, *INDUSTRY_TARGETS))


def _mapping_sort_key(target: IndustryFactTarget) -> tuple[int, str, str]:
    return (target.priority, target.industry_label, target.internal_metric_name)


def _merge_duplicate_targets(targets: Iterable[IndustryFactTarget]) -> tuple[IndustryFactTarget, ...]:
    merged: dict[tuple[str, str, str, str], IndustryFactTarget] = {}
    labels: dict[tuple[str, str, str, str], list[str]] = {}
    for target in targets:
        key = (
            target.taxonomy,
            target.raw_concept,
            target.internal_metric_name,
            target.statement_type,
        )
        current = merged.get(key)
        labels.setdefault(key, [])
        if target.industry_label not in labels[key]:
            labels[key].append(target.industry_label)
        if current is None:
            merged[key] = target
            continue
        notes = "; ".join(note for note in (current.notes, target.notes) if note)
        merged[key] = IndustryFactTarget(
            industry_label=current.industry_label,
            raw_concept=current.raw_concept,
            taxonomy=current.taxonomy,
            internal_metric_name=current.internal_metric_name,
            statement_type=current.statement_type,
            required_for_core=current.required_for_core or target.required_for_core,
            required_for_specialized_indicators=(
                current.required_for_specialized_indicators
                or target.required_for_specialized_indicators
            ),
            consolidated_or_segment=current.consolidated_or_segment,
            priority=min(current.priority, target.priority),
            notes=notes,
        )

    rows: list[IndustryFactTarget] = []
    for key, target in merged.items():
        rows.append(
            IndustryFactTarget(
                industry_label=", ".join(labels[key]),
                raw_concept=target.raw_concept,
                taxonomy=target.taxonomy,
                internal_metric_name=target.internal_metric_name,
                statement_type=target.statement_type,
                required_for_core=target.required_for_core,
                required_for_specialized_indicators=target.required_for_specialized_indicators,
                consolidated_or_segment=target.consolidated_or_segment,
                priority=target.priority,
                notes=target.notes,
            )
        )
    return tuple(sorted(rows, key=lambda target: (target.industry_label, target.statement_type, target.raw_concept)))
