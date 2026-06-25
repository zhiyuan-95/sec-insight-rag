"""Deterministic derived indicator calculation engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from src.indicators.formulas import INDICATOR_DEFINITIONS, INDICATOR_DEFINITIONS_BY_NAME
from src.indicators.models import CALCULATED, SKIPPED, IndicatorDefinition, IndicatorResult
from src.storage.metrics_repository import FinancialMetric

MISSING_REQUIRED_METRIC = "missing_required_metric"
ZERO_DENOMINATOR = "zero_denominator"
MISSING_PRIOR_PERIOD = "missing_prior_period"
ZERO_PRIOR_PERIOD = "zero_prior_period"
UNIT_MISMATCH = "unit_mismatch"
AMBIGUOUS_METRIC_SET = "ambiguous_metric_set"
MISSING_PERIOD_DATES = "missing_period_dates"
NON_POSITIVE_EBITDA = "non_positive_ebitda"
UNSUPPORTED_DEBT_MAPPING = "unsupported_debt_mapping"

PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class _PeriodKey:
    company_id: int
    fiscal_year: int
    fiscal_period: str


@dataclass(frozen=True)
class _MetricValue:
    value: Decimal
    unit: str
    source_metrics: tuple[FinancialMetric, ...]


@dataclass(frozen=True)
class _MetricLookup:
    metrics: dict[_PeriodKey, dict[str, tuple[FinancialMetric, ...]]]
    active_periods: frozenset[_PeriodKey]

    def metric(self, period: _PeriodKey, metric_name: str) -> tuple[FinancialMetric | None, str | None]:
        candidates = self.metrics.get(period, {}).get(metric_name, ())
        candidates = tuple(metric for metric in candidates if metric.value_numeric is not None)
        if not candidates:
            return None, MISSING_REQUIRED_METRIC
        units = {metric.unit for metric in candidates}
        if len(units) > 1:
            return None, AMBIGUOUS_METRIC_SET
        return _best_metric(candidates), None


def calculate_indicators(
    company_id: int,
    metrics: list[FinancialMetric],
    *,
    active_only: bool = True,
) -> list[IndicatorResult]:
    """Calculate the full indicator catalog from base metrics.

    When active_only is true, only active-window periods are emitted, but
    out-of-window metrics remain available as prior-period formula context.
    """
    usable_metrics = [
        metric
        for metric in metrics
        if metric.company_id == company_id
        and metric.fiscal_year is not None
        and metric.fiscal_period is not None
    ]
    lookup = _build_lookup(usable_metrics)
    target_periods = lookup.active_periods if active_only else frozenset(lookup.metrics)
    results: list[IndicatorResult] = []
    for period in sorted(target_periods, key=_period_sort_key):
        for definition in INDICATOR_DEFINITIONS:
            results.append(_calculate_one(definition, period, lookup))
    return results


def _build_lookup(metrics: list[FinancialMetric]) -> _MetricLookup:
    grouped: dict[_PeriodKey, dict[str, list[FinancialMetric]]] = defaultdict(lambda: defaultdict(list))
    active_periods: set[_PeriodKey] = set()
    for metric in metrics:
        if metric.fiscal_year is None or metric.fiscal_period is None:
            continue
        period = _PeriodKey(
            company_id=metric.company_id,
            fiscal_year=metric.fiscal_year,
            fiscal_period=metric.fiscal_period.strip().upper(),
        )
        grouped[period][metric.metric_name].append(metric)
        if metric.is_active_window:
            active_periods.add(period)
    frozen = {
        period: {
            name: tuple(values)
            for name, values in by_name.items()
        }
        for period, by_name in grouped.items()
    }
    return _MetricLookup(metrics=frozen, active_periods=frozenset(active_periods))


def _calculate_one(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    result = _calculate_one_value(definition, period, lookup)
    return replace(result, is_active_window=period in lookup.active_periods)


def _calculate_one_value(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    name = definition.indicator_name
    if name == "revenue_growth_yoy":
        return _growth(definition, period, lookup, "revenue")
    if name == "operating_income_growth_yoy":
        return _growth(definition, period, lookup, "operating_income")
    if name == "diluted_eps_growth_yoy":
        return _growth(definition, period, lookup, "diluted_eps")
    if name == "free_cash_flow_growth_yoy":
        return _free_cash_flow_growth(definition, period, lookup)
    if name == "gross_margin":
        return _ratio(definition, period, lookup, "gross_profit", "revenue")
    if name == "operating_margin":
        return _ratio(definition, period, lookup, "operating_income", "revenue")
    if name == "net_margin":
        return _ratio(definition, period, lookup, "net_income", "revenue")
    if name == "rd_intensity":
        return _ratio(definition, period, lookup, "research_and_development_expense", "revenue")
    if name == "sga_intensity":
        return _ratio(definition, period, lookup, "selling_general_and_administrative_expense", "revenue")
    if name == "cost_of_revenue_ratio":
        return _ratio(definition, period, lookup, "cost_of_revenue", "revenue")
    if name == "return_on_assets":
        return _ratio_to_average(definition, period, lookup, "net_income", "total_assets")
    if name == "return_on_equity":
        return _ratio_to_average(definition, period, lookup, "net_income", "shareholders_equity")
    if name == "asset_turnover":
        return _ratio_to_average(definition, period, lookup, "revenue", "total_assets")
    if name == "operating_cash_flow_margin":
        return _ratio(definition, period, lookup, "operating_cash_flow", "revenue")
    if name == "free_cash_flow":
        return _free_cash_flow_result(definition, period, lookup)
    if name == "free_cash_flow_margin":
        return _free_cash_flow_margin(definition, period, lookup)
    if name == "cash_earnings_conversion":
        return _ratio(definition, period, lookup, "operating_cash_flow", "net_income")
    if name == "capex_intensity":
        return _capex_intensity(definition, period, lookup)
    if name == "current_ratio":
        return _ratio(definition, period, lookup, "current_assets", "current_liabilities")
    if name == "quick_ratio":
        return _quick_ratio(definition, period, lookup)
    if name == "debt_to_equity":
        return _debt_to_equity(definition, period, lookup)
    if name == "net_debt_to_ebitda":
        return _net_debt_to_ebitda(definition, period, lookup)
    if name == "interest_coverage":
        return _interest_coverage(definition, period, lookup)
    if name == "days_sales_outstanding":
        return _days_result(definition, period, lookup, "accounts_receivable", "revenue")
    if name == "days_inventory_outstanding":
        return _days_result(definition, period, lookup, "inventory", "cost_of_revenue")
    if name == "days_payable_outstanding":
        return _days_result(definition, period, lookup, "accounts_payable", "cost_of_revenue")
    if name == "cash_conversion_cycle":
        return _cash_conversion_cycle(definition, period, lookup)
    if name == "share_dilution_rate":
        return _growth(definition, period, lookup, "weighted_average_diluted_shares")
    return _skip(definition, period, MISSING_REQUIRED_METRIC)


def _ratio(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
    numerator_name: str,
    denominator_name: str,
) -> IndicatorResult:
    numerator, skip_reason = _required_metric(lookup, period, numerator_name)
    if numerator is None:
        return _skip(definition, period, skip_reason)
    denominator, skip_reason = _required_metric(lookup, period, denominator_name)
    if denominator is None:
        return _skip(definition, period, skip_reason, (numerator,))
    if numerator.unit != denominator.unit:
        return _skip(definition, period, UNIT_MISMATCH, (numerator, denominator))
    if denominator.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, (numerator, denominator))
    return _calculated(
        definition,
        period,
        numerator.value_numeric / denominator.value_numeric,
        "ratio",
        (numerator, denominator),
    )


def _growth(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
    metric_name: str,
) -> IndicatorResult:
    current, skip_reason = _required_metric(lookup, period, metric_name)
    if current is None:
        return _skip(definition, period, skip_reason)
    prior_period = _prior_comparable_period(period)
    prior, skip_reason = _required_metric(lookup, prior_period, metric_name)
    if prior is None:
        reason = MISSING_PRIOR_PERIOD if skip_reason == MISSING_REQUIRED_METRIC else skip_reason
        return _skip(definition, period, reason, (current,))
    if current.unit != prior.unit:
        return _skip(definition, period, UNIT_MISMATCH, (current, prior))
    if prior.value_numeric == 0:
        return _skip(definition, period, ZERO_PRIOR_PERIOD, (current, prior))
    value = (current.value_numeric - prior.value_numeric) / abs(prior.value_numeric)
    return _calculated(definition, period, value, "ratio", (current, prior))


def _ratio_to_average(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
    numerator_name: str,
    average_metric_name: str,
) -> IndicatorResult:
    numerator, skip_reason = _required_metric(lookup, period, numerator_name)
    if numerator is None:
        return _skip(definition, period, skip_reason)
    average, skip_reason = _average_metric(lookup, period, average_metric_name)
    if average is None:
        return _skip(definition, period, skip_reason, (numerator,))
    if numerator.unit != average.unit:
        return _skip(definition, period, UNIT_MISMATCH, (numerator, *average.source_metrics))
    if average.value == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, (numerator, *average.source_metrics))
    return _calculated(
        definition,
        period,
        numerator.value_numeric / average.value,
        "ratio",
        (numerator, *average.source_metrics),
    )


def _free_cash_flow_result(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    free_cash_flow, skip_reason = _free_cash_flow(lookup, period)
    if free_cash_flow is None:
        return _skip(definition, period, skip_reason)
    return _calculated(
        definition,
        period,
        free_cash_flow.value,
        free_cash_flow.unit,
        free_cash_flow.source_metrics,
    )


def _free_cash_flow_margin(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    free_cash_flow, skip_reason = _free_cash_flow(lookup, period)
    if free_cash_flow is None:
        return _skip(definition, period, skip_reason)
    revenue, skip_reason = _required_metric(lookup, period, "revenue")
    if revenue is None:
        return _skip(definition, period, skip_reason, free_cash_flow.source_metrics)
    if free_cash_flow.unit != revenue.unit:
        return _skip(definition, period, UNIT_MISMATCH, (*free_cash_flow.source_metrics, revenue))
    if revenue.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, (*free_cash_flow.source_metrics, revenue))
    return _calculated(
        definition,
        period,
        free_cash_flow.value / revenue.value_numeric,
        "ratio",
        (*free_cash_flow.source_metrics, revenue),
    )


def _free_cash_flow_growth(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    current, skip_reason = _free_cash_flow(lookup, period)
    if current is None:
        return _skip(definition, period, skip_reason)
    prior_period = _prior_comparable_period(period)
    prior, skip_reason = _free_cash_flow(lookup, prior_period)
    if prior is None:
        reason = MISSING_PRIOR_PERIOD if skip_reason == MISSING_REQUIRED_METRIC else skip_reason
        return _skip(definition, period, reason, current.source_metrics)
    if current.unit != prior.unit:
        return _skip(definition, period, UNIT_MISMATCH, (*current.source_metrics, *prior.source_metrics))
    if prior.value == 0:
        return _skip(definition, period, ZERO_PRIOR_PERIOD, (*current.source_metrics, *prior.source_metrics))
    value = (current.value - prior.value) / abs(prior.value)
    return _calculated(definition, period, value, "ratio", (*current.source_metrics, *prior.source_metrics))


def _capex_intensity(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    capex, skip_reason = _required_metric(lookup, period, "capital_expenditure")
    if capex is None:
        return _skip(definition, period, skip_reason)
    revenue, skip_reason = _required_metric(lookup, period, "revenue")
    if revenue is None:
        return _skip(definition, period, skip_reason, (capex,))
    if capex.unit != revenue.unit:
        return _skip(definition, period, UNIT_MISMATCH, (capex, revenue))
    if revenue.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, (capex, revenue))
    return _calculated(definition, period, abs(capex.value_numeric) / revenue.value_numeric, "ratio", (capex, revenue))


def _quick_ratio(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    cash, investments, receivables, liabilities = _required_metrics(
        lookup,
        period,
        ("cash_and_equivalents", "short_term_investments", "accounts_receivable", "current_liabilities"),
    )
    sources = tuple(metric for metric in (cash, investments, receivables, liabilities) if metric is not None)
    if None in (cash, investments, receivables, liabilities):
        return _skip(definition, period, MISSING_REQUIRED_METRIC, sources)
    if not _units_match(sources):
        return _skip(definition, period, UNIT_MISMATCH, sources)
    if liabilities.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, sources)
    value = (cash.value_numeric + investments.value_numeric + receivables.value_numeric) / liabilities.value_numeric
    return _calculated(definition, period, value, "ratio", sources)


def _debt_to_equity(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    total_debt, skip_reason = _total_debt(lookup, period)
    if total_debt is None:
        return _skip(definition, period, skip_reason)
    equity, skip_reason = _required_metric(lookup, period, "shareholders_equity")
    if equity is None:
        return _skip(definition, period, skip_reason, total_debt.source_metrics)
    if total_debt.unit != equity.unit:
        return _skip(definition, period, UNIT_MISMATCH, (*total_debt.source_metrics, equity))
    if equity.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, (*total_debt.source_metrics, equity))
    return _calculated(
        definition,
        period,
        total_debt.value / equity.value_numeric,
        "ratio",
        (*total_debt.source_metrics, equity),
    )


def _net_debt_to_ebitda(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    total_debt, skip_reason = _total_debt(lookup, period)
    if total_debt is None:
        return _skip(definition, period, skip_reason)
    cash, investments, operating_income = _required_metrics(
        lookup,
        period,
        (
            "cash_and_equivalents",
            "short_term_investments",
            "operating_income",
        ),
    )
    depreciation, depreciation_skip_reason = _depreciation_and_amortization(lookup, period)
    extra_sources = tuple(metric for metric in (cash, investments, operating_income) if metric is not None)
    depreciation_sources = depreciation.source_metrics if depreciation is not None else ()
    sources = (*total_debt.source_metrics, *extra_sources, *depreciation_sources)
    if None in (cash, investments, operating_income):
        return _skip(definition, period, MISSING_REQUIRED_METRIC, sources)
    if depreciation is None:
        return _skip(definition, period, depreciation_skip_reason, sources)
    if not _units_match(sources):
        return _skip(definition, period, UNIT_MISMATCH, sources)
    ebitda = operating_income.value_numeric + depreciation.value
    if ebitda <= 0:
        return _skip(definition, period, NON_POSITIVE_EBITDA, sources)
    net_debt = total_debt.value - cash.value_numeric - investments.value_numeric
    return _calculated(definition, period, net_debt / ebitda, "ratio", sources)


def _interest_coverage(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    operating_income, interest = _required_metrics(lookup, period, ("operating_income", "interest_expense"))
    sources = tuple(metric for metric in (operating_income, interest) if metric is not None)
    if operating_income is None or interest is None:
        return _skip(definition, period, MISSING_REQUIRED_METRIC, sources)
    if operating_income.unit != interest.unit:
        return _skip(definition, period, UNIT_MISMATCH, sources)
    if interest.value_numeric == 0:
        return _skip(definition, period, ZERO_DENOMINATOR, sources)
    return _calculated(
        definition,
        period,
        operating_income.value_numeric / abs(interest.value_numeric),
        "ratio",
        sources,
    )


def _days_result(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
    average_metric_name: str,
    denominator_metric_name: str,
) -> IndicatorResult:
    value, skip_reason = _days_value(lookup, period, average_metric_name, denominator_metric_name)
    if value is None:
        return _skip(definition, period, skip_reason)
    return _calculated(definition, period, value.value, "days", value.source_metrics)


def _cash_conversion_cycle(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    lookup: _MetricLookup,
) -> IndicatorResult:
    dso, skip_reason = _days_value(lookup, period, "accounts_receivable", "revenue")
    if dso is None:
        return _skip(definition, period, skip_reason)
    dio, skip_reason = _days_value(lookup, period, "inventory", "cost_of_revenue")
    if dio is None:
        return _skip(definition, period, skip_reason, dso.source_metrics)
    dpo, skip_reason = _days_value(lookup, period, "accounts_payable", "cost_of_revenue")
    if dpo is None:
        return _skip(definition, period, skip_reason, (*dso.source_metrics, *dio.source_metrics))
    sources = (*dso.source_metrics, *dio.source_metrics, *dpo.source_metrics)
    value = dso.value + dio.value - dpo.value
    return _calculated(definition, period, value, "days", sources)


def _free_cash_flow(
    lookup: _MetricLookup,
    period: _PeriodKey,
) -> tuple[_MetricValue | None, str]:
    operating_cash_flow, capex = _required_metrics(
        lookup,
        period,
        ("operating_cash_flow", "capital_expenditure"),
    )
    sources = tuple(metric for metric in (operating_cash_flow, capex) if metric is not None)
    if operating_cash_flow is None or capex is None:
        return None, MISSING_REQUIRED_METRIC
    if operating_cash_flow.unit != capex.unit:
        return None, UNIT_MISMATCH
    value = operating_cash_flow.value_numeric - abs(capex.value_numeric)
    return _MetricValue(value=value, unit=operating_cash_flow.unit, source_metrics=sources), ""


def _average_metric(
    lookup: _MetricLookup,
    period: _PeriodKey,
    metric_name: str,
) -> tuple[_MetricValue | None, str]:
    current, skip_reason = _required_metric(lookup, period, metric_name)
    if current is None:
        return None, skip_reason
    prior_period = _prior_comparable_period(period)
    prior, skip_reason = _required_metric(lookup, prior_period, metric_name)
    if prior is None:
        reason = MISSING_PRIOR_PERIOD if skip_reason == MISSING_REQUIRED_METRIC else skip_reason
        return None, reason
    if current.unit != prior.unit:
        return None, UNIT_MISMATCH
    return (
        _MetricValue(
            value=(current.value_numeric + prior.value_numeric) / Decimal("2"),
            unit=current.unit,
            source_metrics=(current, prior),
        ),
        "",
    )


def _days_value(
    lookup: _MetricLookup,
    period: _PeriodKey,
    average_metric_name: str,
    denominator_metric_name: str,
) -> tuple[_MetricValue | None, str]:
    average, skip_reason = _average_metric(lookup, period, average_metric_name)
    if average is None:
        return None, skip_reason
    denominator, skip_reason = _required_metric(lookup, period, denominator_metric_name)
    if denominator is None:
        return None, skip_reason
    sources = (*average.source_metrics, denominator)
    if average.unit != denominator.unit:
        return None, UNIT_MISMATCH
    if denominator.value_numeric == 0:
        return None, ZERO_DENOMINATOR
    period_days = _period_days(denominator)
    if period_days is None:
        return None, MISSING_PERIOD_DATES
    value = (average.value / denominator.value_numeric) * Decimal(period_days)
    return _MetricValue(value=value, unit="days", source_metrics=sources), ""


def _depreciation_and_amortization(
    lookup: _MetricLookup,
    period: _PeriodKey,
) -> tuple[_MetricValue | None, str]:
    direct, skip_reason = _required_metric(lookup, period, "depreciation_and_amortization")
    if direct is not None:
        return _MetricValue(value=direct.value_numeric, unit=direct.unit, source_metrics=(direct,)), ""
    if skip_reason != MISSING_REQUIRED_METRIC:
        return None, skip_reason or MISSING_REQUIRED_METRIC

    depreciation, amortization = _required_metrics(
        lookup,
        period,
        ("depreciation", "amortization_of_intangible_assets"),
    )
    sources = tuple(metric for metric in (depreciation, amortization) if metric is not None)
    if depreciation is None or amortization is None:
        return None, MISSING_REQUIRED_METRIC
    if not _units_match(sources):
        return None, UNIT_MISMATCH
    return (
        _MetricValue(
            value=depreciation.value_numeric + amortization.value_numeric,
            unit=depreciation.unit,
            source_metrics=sources,
        ),
        "",
    )


def _total_debt(
    lookup: _MetricLookup,
    period: _PeriodKey,
) -> tuple[_MetricValue | None, str]:
    component_groups = (
        (
            "long_term_debt_and_finance_lease_obligations_current",
            "long_term_debt_and_finance_lease_obligations_noncurrent",
        ),
        (
            "long_term_debt_current",
            "long_term_debt_noncurrent",
            "finance_lease_liability_current",
            "finance_lease_liability_noncurrent",
        ),
        (
            "debt_current",
            "debt_noncurrent",
            "finance_lease_liability_current",
            "finance_lease_liability_noncurrent",
        ),
        ("long_term_debt_current", "long_term_debt_noncurrent"),
        ("debt_current", "debt_noncurrent"),
        (
            "debt_current",
            "finance_lease_liability_current",
            "finance_lease_liability_noncurrent",
        ),
        ("finance_lease_liability_current", "finance_lease_liability_noncurrent"),
    )
    for group in component_groups:
        components = _required_metrics(lookup, period, group)
        if any(component is None for component in components):
            continue
        if not _units_match(components):
            return None, UNIT_MISMATCH
        value = sum((component.value_numeric for component in components), Decimal("0"))
        return _MetricValue(value=value, unit=components[0].unit, source_metrics=components), ""
    return None, UNSUPPORTED_DEBT_MAPPING


def _required_metric(
    lookup: _MetricLookup,
    period: _PeriodKey,
    metric_name: str,
) -> tuple[FinancialMetric | None, str | None]:
    return lookup.metric(period, metric_name)


def _required_metrics(
    lookup: _MetricLookup,
    period: _PeriodKey,
    metric_names: tuple[str, ...],
) -> tuple[FinancialMetric | None, ...]:
    return tuple(_required_metric(lookup, period, name)[0] for name in metric_names)


def _calculated(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    value: Decimal,
    unit: str,
    source_metrics: tuple[FinancialMetric, ...],
) -> IndicatorResult:
    return _indicator_result(
        definition=definition,
        period=period,
        value_numeric=value,
        unit=unit,
        source_metrics=source_metrics,
        calculation_status=CALCULATED,
        skip_reason=None,
    )


def _skip(
    definition: IndicatorDefinition,
    period: _PeriodKey,
    skip_reason: str | None,
    source_metrics: tuple[FinancialMetric, ...] = (),
) -> IndicatorResult:
    return _indicator_result(
        definition=definition,
        period=period,
        value_numeric=None,
        unit=definition.output_unit,
        source_metrics=source_metrics,
        calculation_status=SKIPPED,
        skip_reason=skip_reason or MISSING_REQUIRED_METRIC,
    )


def _indicator_result(
    *,
    definition: IndicatorDefinition,
    period: _PeriodKey,
    value_numeric: Decimal | None,
    unit: str,
    source_metrics: tuple[FinancialMetric, ...],
    calculation_status: str,
    skip_reason: str | None,
) -> IndicatorResult:
    unique_sources = _unique_metrics(source_metrics)
    current_sources = [
        metric
        for metric in unique_sources
        if metric.fiscal_year == period.fiscal_year
        and (metric.fiscal_period or "").strip().upper() == period.fiscal_period
    ] or list(unique_sources)
    return IndicatorResult(
        company_id=period.company_id,
        indicator_name=definition.indicator_name,
        formula_name=definition.formula_name,
        formula_version=definition.formula_version,
        value_numeric=value_numeric,
        unit=unit,
        period_type=definition.period_type,
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        start_date=_min_date(metric.start_date for metric in current_sources),
        end_date=_max_date(metric.end_date for metric in current_sources),
        filing_date=_max_date(metric.filing_date for metric in current_sources),
        source_metric_ids=tuple(
            sorted(metric.metric_id for metric in unique_sources if metric.metric_id is not None)
        ),
        source_raw_fact_ids=tuple(
            sorted(metric.raw_fact_id for metric in unique_sources if metric.raw_fact_id is not None)
        ),
        source_accession_numbers=tuple(
            sorted({metric.accession_number for metric in unique_sources if metric.accession_number})
        ),
        is_active_window=all(metric.is_active_window for metric in unique_sources) if unique_sources else True,
        calculation_status=calculation_status,
        skip_reason=skip_reason,
    )


def _best_metric(candidates: tuple[FinancialMetric, ...]) -> FinancialMetric:
    return sorted(
        candidates,
        key=lambda metric: (
            metric.filing_date or date.min,
            metric.accession_number,
            metric.metric_id or 0,
        ),
    )[-1]


def _prior_comparable_period(period: _PeriodKey) -> _PeriodKey:
    return _PeriodKey(
        company_id=period.company_id,
        fiscal_year=period.fiscal_year - 1,
        fiscal_period=period.fiscal_period,
    )


def _period_days(metric: FinancialMetric) -> int | None:
    if metric.start_date is None or metric.end_date is None:
        return None
    days = (metric.end_date - metric.start_date).days
    return days if days > 0 else None


def _period_sort_key(period: _PeriodKey) -> tuple[int, int]:
    return (
        period.fiscal_year,
        PERIOD_ORDER.get(period.fiscal_period, 0),
    )


def _units_match(metrics: tuple[FinancialMetric, ...]) -> bool:
    return len({metric.unit for metric in metrics}) == 1


def _unique_metrics(metrics: tuple[FinancialMetric, ...]) -> tuple[FinancialMetric, ...]:
    unique: dict[tuple[int | None, str, str], FinancialMetric] = {}
    for metric in metrics:
        key = (metric.metric_id, metric.metric_name, metric.accession_number)
        unique[key] = metric
    return tuple(unique.values())


def _min_date(values: object) -> date | None:
    dates = [value for value in values if isinstance(value, date)]
    return min(dates) if dates else None


def _max_date(values: object) -> date | None:
    dates = [value for value in values if isinstance(value, date)]
    return max(dates) if dates else None


def indicator_names() -> tuple[str, ...]:
    """Return supported indicator names in registry order."""
    return tuple(definition.indicator_name for definition in INDICATOR_DEFINITIONS)


def formula_text(indicator_name: str) -> str:
    """Return the registered formula text for one indicator."""
    return INDICATOR_DEFINITIONS_BY_NAME[indicator_name].formula_text
