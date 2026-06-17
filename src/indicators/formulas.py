"""Formula registry for deterministic derived indicators."""

from __future__ import annotations

from src.indicators.models import IndicatorDefinition

FORMULA_VERSION = "v1"


def _definition(
    indicator_name: str,
    formula_text: str,
    required_metric_names: tuple[str, ...],
    *,
    output_unit: str = "ratio",
    period_type: str = "duration",
) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_name=indicator_name,
        formula_name=indicator_name,
        formula_version=FORMULA_VERSION,
        formula_text=formula_text,
        required_metric_names=required_metric_names,
        output_unit=output_unit,
        period_type=period_type,
    )


INDICATOR_DEFINITIONS: tuple[IndicatorDefinition, ...] = (
    _definition(
        "revenue_growth_yoy",
        "(revenue_t - revenue_t_minus_1) / abs(revenue_t_minus_1)",
        ("revenue",),
    ),
    _definition(
        "operating_income_growth_yoy",
        "(operating_income_t - operating_income_t_minus_1) / abs(operating_income_t_minus_1)",
        ("operating_income",),
    ),
    _definition(
        "diluted_eps_growth_yoy",
        "(diluted_eps_t - diluted_eps_t_minus_1) / abs(diluted_eps_t_minus_1)",
        ("diluted_eps",),
    ),
    _definition(
        "free_cash_flow_growth_yoy",
        "(free_cash_flow_t - free_cash_flow_t_minus_1) / abs(free_cash_flow_t_minus_1)",
        ("operating_cash_flow", "capital_expenditure"),
    ),
    _definition("gross_margin", "gross_profit / revenue", ("gross_profit", "revenue")),
    _definition("operating_margin", "operating_income / revenue", ("operating_income", "revenue")),
    _definition("net_margin", "net_income / revenue", ("net_income", "revenue")),
    _definition(
        "rd_intensity",
        "research_and_development_expense / revenue",
        ("research_and_development_expense", "revenue"),
    ),
    _definition(
        "sga_intensity",
        "selling_general_and_administrative_expense / revenue",
        ("selling_general_and_administrative_expense", "revenue"),
    ),
    _definition("cost_of_revenue_ratio", "cost_of_revenue / revenue", ("cost_of_revenue", "revenue")),
    _definition(
        "return_on_assets",
        "net_income / average_total_assets",
        ("net_income", "total_assets"),
        period_type="mixed",
    ),
    _definition(
        "return_on_equity",
        "net_income / average_shareholders_equity",
        ("net_income", "shareholders_equity"),
        period_type="mixed",
    ),
    _definition(
        "asset_turnover",
        "revenue / average_total_assets",
        ("revenue", "total_assets"),
        period_type="mixed",
    ),
    _definition(
        "operating_cash_flow_margin",
        "operating_cash_flow / revenue",
        ("operating_cash_flow", "revenue"),
    ),
    _definition(
        "free_cash_flow",
        "operating_cash_flow - abs(capital_expenditure)",
        ("operating_cash_flow", "capital_expenditure"),
        output_unit="source_currency",
    ),
    _definition(
        "free_cash_flow_margin",
        "free_cash_flow / revenue",
        ("operating_cash_flow", "capital_expenditure", "revenue"),
    ),
    _definition(
        "cash_earnings_conversion",
        "operating_cash_flow / net_income",
        ("operating_cash_flow", "net_income"),
    ),
    _definition(
        "capex_intensity",
        "abs(capital_expenditure) / revenue",
        ("capital_expenditure", "revenue"),
    ),
    _definition(
        "current_ratio",
        "current_assets / current_liabilities",
        ("current_assets", "current_liabilities"),
        period_type="instant",
    ),
    _definition(
        "quick_ratio",
        "(cash_and_equivalents + short_term_investments + accounts_receivable) / current_liabilities",
        ("cash_and_equivalents", "short_term_investments", "accounts_receivable", "current_liabilities"),
        period_type="instant",
    ),
    _definition(
        "debt_to_equity",
        "total_debt / shareholders_equity",
        ("approved_debt_components", "shareholders_equity"),
        period_type="instant",
    ),
    _definition(
        "net_debt_to_ebitda",
        "(total_debt - cash_and_equivalents - short_term_investments) / "
        "(operating_income + depreciation_and_amortization)",
        (
            "approved_debt_components",
            "cash_and_equivalents",
            "short_term_investments",
            "operating_income",
            "depreciation_and_amortization",
        ),
        period_type="mixed",
    ),
    _definition(
        "interest_coverage",
        "operating_income / abs(interest_expense)",
        ("operating_income", "interest_expense"),
    ),
    _definition(
        "days_sales_outstanding",
        "(average_accounts_receivable / revenue) * period_days",
        ("accounts_receivable", "revenue"),
        output_unit="days",
        period_type="mixed",
    ),
    _definition(
        "days_inventory_outstanding",
        "(average_inventory / cost_of_revenue) * period_days",
        ("inventory", "cost_of_revenue"),
        output_unit="days",
        period_type="mixed",
    ),
    _definition(
        "days_payable_outstanding",
        "(average_accounts_payable / cost_of_revenue) * period_days",
        ("accounts_payable", "cost_of_revenue"),
        output_unit="days",
        period_type="mixed",
    ),
    _definition(
        "cash_conversion_cycle",
        "days_sales_outstanding + days_inventory_outstanding - days_payable_outstanding",
        ("accounts_receivable", "inventory", "accounts_payable", "revenue", "cost_of_revenue"),
        output_unit="days",
        period_type="mixed",
    ),
    _definition(
        "share_dilution_rate",
        "(weighted_average_diluted_shares_t - weighted_average_diluted_shares_t_minus_1) / "
        "abs(weighted_average_diluted_shares_t_minus_1)",
        ("weighted_average_diluted_shares",),
    ),
)

INDICATOR_DEFINITIONS_BY_NAME = {
    definition.indicator_name: definition
    for definition in INDICATOR_DEFINITIONS
}
