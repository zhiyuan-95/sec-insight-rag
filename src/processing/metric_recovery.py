"""Report-only recovery diagnostics for missing mapped base metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

TARGET_DIRECT_MAPPED = "direct_mapped"
TARGET_DERIVED_FROM_COMPONENTS = "derived_from_components"
TARGET_DECOMPOSITION_INCOMPLETE = "decomposition_incomplete"
TARGET_UNSUPPORTED_RECOVERY = "unsupported_recovery"

COMPONENT_MAPPED = "component_mapped"
COMPONENT_ASSUMED_ZERO = "assumed_zero_component"
COMPONENT_MISSING_REQUIRED = "component_missing_required"
COMPONENT_AMBIGUOUS = "component_ambiguous"

REVIEW_NOT_REVIEWED = "not_reviewed"
REVIEW_APPROVED = "approved"

SKIP_MISSING_REQUIRED_COMPONENT = "recovery_skipped_missing_required_component"
SKIP_UNIT_MISMATCH = "recovery_skipped_unit_mismatch"
SKIP_PERIOD_MISMATCH = "recovery_skipped_period_mismatch"
SKIP_DUPLICATE_COMPONENT_FACTS = "recovery_skipped_duplicate_component_facts"

FORMULA_VERSION = "v1"


@dataclass(frozen=True)
class MetricRecoverySource:
    """A mapped base metric available to report-only recovery diagnostics."""

    metric_name: str
    statement_type: str
    value_numeric: Decimal | None
    unit: str
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    accession_number: str
    metric_id: int | None = None
    raw_fact_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    filing_date: date | None = None
    is_active_window: bool = True
    company_id: int | None = None


@dataclass(frozen=True)
class RecoveryComponentDefinition:
    """One source-controlled component policy inside a recovery formula."""

    component_name: str
    metric_names: tuple[str, ...]
    required: bool
    zero_if_absent: bool
    notes: str = ""


@dataclass(frozen=True)
class RecoveryFormulaDefinition:
    """A source-controlled formula variant for one target metric."""

    formula_name: str
    target_metric_name: str
    target_xbrl_concept: str
    components: tuple[RecoveryComponentDefinition, ...]


@dataclass(frozen=True)
class MetricRecoveryComponentResult:
    """Report evidence for one component lookup."""

    component_name: str
    component_status: str
    metric_names: tuple[str, ...]
    value_numeric: Decimal | None = None
    unit: str | None = None
    source_metric_ids: tuple[int, ...] = ()
    source_raw_fact_ids: tuple[int, ...] = ()
    source_accession_numbers: tuple[str, ...] = ()
    coverage_proof: tuple[str, ...] = ()
    skip_reason: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class MetricRecoveryResult:
    """Report-only recovery result for one target and fiscal period."""

    target_metric_name: str
    target_xbrl_concept: str
    target_recovery_status: str
    formula_name: str | None
    formula_version: str
    fiscal_year: int | None
    fiscal_period: str | None
    period_type: str
    value_numeric: Decimal | None
    unit: str | None
    source_metric_ids: tuple[int, ...]
    source_raw_fact_ids: tuple[int, ...]
    source_accession_numbers: tuple[str, ...]
    assumed_zero_components: tuple[str, ...]
    missing_required_components: tuple[str, ...]
    review_status: str
    skip_reason: str | None
    components: tuple[MetricRecoveryComponentResult, ...]


@dataclass(frozen=True)
class _PeriodKey:
    company_id: int | None
    fiscal_year: int
    fiscal_period: str
    period_type: str


@dataclass(frozen=True)
class _FormulaEvaluation:
    formula: RecoveryFormulaDefinition
    components: tuple[MetricRecoveryComponentResult, ...]
    value_numeric: Decimal | None
    unit: str | None
    skip_reason: str | None
    review_status: str

    @property
    def is_success(self) -> bool:
        return self.skip_reason is None and self.value_numeric is not None


DEBT_RECOVERY_FORMULAS: tuple[RecoveryFormulaDefinition, ...] = (
    RecoveryFormulaDefinition(
        formula_name="debt_current_combined_long_term_and_finance_lease",
        target_metric_name="debt_current",
        target_xbrl_concept="DebtCurrent",
        components=(
            RecoveryComponentDefinition(
                component_name="current_long_term_debt_and_finance_lease_obligations",
                metric_names=("long_term_debt_and_finance_lease_obligations_current",),
                required=True,
                zero_if_absent=False,
            ),
            RecoveryComponentDefinition(
                component_name="short_term_borrowings",
                metric_names=("short_term_borrowings",),
                required=False,
                zero_if_absent=True,
            ),
        ),
    ),
    RecoveryFormulaDefinition(
        formula_name="debt_current_components",
        target_metric_name="debt_current",
        target_xbrl_concept="DebtCurrent",
        components=(
            RecoveryComponentDefinition(
                component_name="current_portion_of_long_term_debt",
                metric_names=("long_term_debt_current",),
                required=True,
                zero_if_absent=False,
            ),
            RecoveryComponentDefinition(
                component_name="short_term_borrowings",
                metric_names=("short_term_borrowings",),
                required=False,
                zero_if_absent=True,
            ),
            RecoveryComponentDefinition(
                component_name="current_finance_lease_debt",
                metric_names=("finance_lease_liability_current",),
                required=False,
                zero_if_absent=True,
            ),
        ),
    ),
    RecoveryFormulaDefinition(
        formula_name="debt_noncurrent_combined_long_term_and_finance_lease",
        target_metric_name="debt_noncurrent",
        target_xbrl_concept="DebtNoncurrent",
        components=(
            RecoveryComponentDefinition(
                component_name="noncurrent_long_term_debt_and_finance_lease_obligations",
                metric_names=("long_term_debt_and_finance_lease_obligations_noncurrent",),
                required=True,
                zero_if_absent=False,
            ),
        ),
    ),
    RecoveryFormulaDefinition(
        formula_name="debt_noncurrent_components",
        target_metric_name="debt_noncurrent",
        target_xbrl_concept="DebtNoncurrent",
        components=(
            RecoveryComponentDefinition(
                component_name="long_term_debt_noncurrent",
                metric_names=("long_term_debt_noncurrent",),
                required=True,
                zero_if_absent=False,
            ),
            RecoveryComponentDefinition(
                component_name="noncurrent_finance_lease_debt",
                metric_names=("finance_lease_liability_noncurrent",),
                required=False,
                zero_if_absent=True,
            ),
        ),
    ),
)

DEBT_TARGET_CONCEPTS = {
    "debt_current": "DebtCurrent",
    "debt_noncurrent": "DebtNoncurrent",
}
DEBT_TARGET_METRIC_NAMES = tuple(DEBT_TARGET_CONCEPTS)
DEBT_COMPONENT_METRIC_NAMES = tuple(
    dict.fromkeys(
        metric_name
        for formula in DEBT_RECOVERY_FORMULAS
        for component in formula.components
        for metric_name in component.metric_names
    )
)


def recover_debt_metrics(
    metrics: Iterable[MetricRecoverySource],
    *,
    active_only: bool = True,
) -> tuple[MetricRecoveryResult, ...]:
    """Return report-only debt recovery diagnostics for mapped base metrics."""
    metric_rows = tuple(
        metric
        for metric in metrics
        if metric.value_numeric is not None
        and metric.fiscal_year is not None
        and metric.fiscal_period
        and metric.statement_type == "balance_sheet"
        and (metric.is_active_window or not active_only)
    )
    if not metric_rows:
        return ()
    periods = _periods_for_recovery(metric_rows)
    results: list[MetricRecoveryResult] = []
    for period in periods:
        for target_metric_name, target_xbrl_concept in DEBT_TARGET_CONCEPTS.items():
            results.append(
                _recover_one_target(
                    metric_rows,
                    period=period,
                    target_metric_name=target_metric_name,
                    target_xbrl_concept=target_xbrl_concept,
                )
            )
    return tuple(results)


def _periods_for_recovery(metrics: tuple[MetricRecoverySource, ...]) -> tuple[_PeriodKey, ...]:
    relevant_names = {*DEBT_TARGET_METRIC_NAMES, *DEBT_COMPONENT_METRIC_NAMES}
    periods = {
        _PeriodKey(
            company_id=metric.company_id,
            fiscal_year=int(metric.fiscal_year),
            fiscal_period=str(metric.fiscal_period).strip().upper(),
            period_type=metric.period_type,
        )
        for metric in metrics
        if metric.metric_name in relevant_names and metric.fiscal_year is not None and metric.fiscal_period
    }
    return tuple(
        sorted(
            periods,
            key=lambda period: (
                period.company_id or 0,
                period.fiscal_year,
                period.fiscal_period,
                period.period_type,
            ),
        )
    )


def _recover_one_target(
    metrics: tuple[MetricRecoverySource, ...],
    *,
    period: _PeriodKey,
    target_metric_name: str,
    target_xbrl_concept: str,
) -> MetricRecoveryResult:
    direct = _component_from_metric_names(
        metrics,
        period=period,
        component_name=target_metric_name,
        metric_names=(target_metric_name,),
        required=True,
        zero_if_absent=False,
    )
    if direct.component_status == COMPONENT_MAPPED and direct.value_numeric is not None:
        return MetricRecoveryResult(
            target_metric_name=target_metric_name,
            target_xbrl_concept=target_xbrl_concept,
            target_recovery_status=TARGET_DIRECT_MAPPED,
            formula_name=None,
            formula_version=FORMULA_VERSION,
            fiscal_year=period.fiscal_year,
            fiscal_period=period.fiscal_period,
            period_type=period.period_type,
            value_numeric=direct.value_numeric,
            unit=direct.unit,
            source_metric_ids=direct.source_metric_ids,
            source_raw_fact_ids=direct.source_raw_fact_ids,
            source_accession_numbers=direct.source_accession_numbers,
            assumed_zero_components=(),
            missing_required_components=(),
            review_status=REVIEW_APPROVED,
            skip_reason=None,
            components=(direct,),
        )
    if direct.skip_reason in {SKIP_DUPLICATE_COMPONENT_FACTS, SKIP_UNIT_MISMATCH}:
        return _incomplete_result(
            period=period,
            target_metric_name=target_metric_name,
            target_xbrl_concept=target_xbrl_concept,
            formula_name=None,
            components=(direct,),
            skip_reason=direct.skip_reason,
            review_status=REVIEW_NOT_REVIEWED,
        )

    evaluations = [
        _evaluate_formula(
            formula,
            metrics,
            period=period,
        )
        for formula in DEBT_RECOVERY_FORMULAS
        if formula.target_metric_name == target_metric_name
    ]
    successful = next((evaluation for evaluation in evaluations if evaluation.is_success), None)
    if successful is not None:
        return _derived_result(period, successful)
    if evaluations:
        return _incomplete_result_from_evaluation(
            period,
            target_metric_name=target_metric_name,
            target_xbrl_concept=target_xbrl_concept,
            evaluation=_select_failure(evaluations),
        )
    return _incomplete_result(
        period=period,
        target_metric_name=target_metric_name,
        target_xbrl_concept=target_xbrl_concept,
        formula_name=None,
        components=(),
        skip_reason=SKIP_MISSING_REQUIRED_COMPONENT,
        review_status=REVIEW_NOT_REVIEWED,
        target_status=TARGET_UNSUPPORTED_RECOVERY,
    )


def _evaluate_formula(
    formula: RecoveryFormulaDefinition,
    metrics: tuple[MetricRecoverySource, ...],
    *,
    period: _PeriodKey,
) -> _FormulaEvaluation:
    component_results = tuple(
        _component_from_metric_names(
            metrics,
            period=period,
            component_name=component.component_name,
            metric_names=component.metric_names,
            required=component.required,
            zero_if_absent=component.zero_if_absent,
        )
        for component in formula.components
    )
    skip_reason = _formula_skip_reason(component_results)
    if skip_reason is not None:
        return _FormulaEvaluation(
            formula=formula,
            components=component_results,
            value_numeric=None,
            unit=None,
            skip_reason=skip_reason,
            review_status=REVIEW_NOT_REVIEWED,
        )
    mapped_components = [
        result
        for result in component_results
        if result.component_status == COMPONENT_MAPPED and result.value_numeric is not None
    ]
    units = {result.unit for result in mapped_components if result.unit}
    if len(units) > 1:
        return _FormulaEvaluation(
            formula=formula,
            components=component_results,
            value_numeric=None,
            unit=None,
            skip_reason=SKIP_UNIT_MISMATCH,
            review_status=REVIEW_NOT_REVIEWED,
        )
    value = sum((result.value_numeric or Decimal("0") for result in component_results), Decimal("0"))
    return _FormulaEvaluation(
        formula=formula,
        components=component_results,
        value_numeric=value,
        unit=next(iter(units), None),
        skip_reason=None,
        review_status=REVIEW_APPROVED,
    )


def _component_from_metric_names(
    metrics: tuple[MetricRecoverySource, ...],
    *,
    period: _PeriodKey,
    component_name: str,
    metric_names: tuple[str, ...],
    required: bool,
    zero_if_absent: bool,
) -> MetricRecoveryComponentResult:
    exact = tuple(
        metric
        for metric in metrics
        if metric.metric_name in metric_names and _period_matches(metric, period)
    )
    if exact:
        units = {metric.unit for metric in exact}
        if len(units) > 1:
            return _component_result_from_sources(
                component_name,
                COMPONENT_AMBIGUOUS,
                metric_names,
                exact,
                skip_reason=SKIP_UNIT_MISMATCH,
                notes="Component facts use incompatible units.",
            )
        if len(exact) > 1:
            return _component_result_from_sources(
                component_name,
                COMPONENT_AMBIGUOUS,
                metric_names,
                exact,
                skip_reason=SKIP_DUPLICATE_COMPONENT_FACTS,
                notes="More than one same-period component fact is usable.",
            )
        metric = exact[0]
        return MetricRecoveryComponentResult(
            component_name=component_name,
            component_status=COMPONENT_MAPPED,
            metric_names=metric_names,
            value_numeric=metric.value_numeric,
            unit=metric.unit,
            source_metric_ids=_metric_ids((metric,)),
            source_raw_fact_ids=_raw_fact_ids((metric,)),
            source_accession_numbers=_accessions((metric,)),
            notes="Mapped base metric used as formula component.",
        )

    if _has_period_mismatch(metrics, period=period, metric_names=metric_names):
        return MetricRecoveryComponentResult(
            component_name=component_name,
            component_status=COMPONENT_AMBIGUOUS,
            metric_names=metric_names,
            skip_reason=SKIP_PERIOD_MISMATCH,
            notes="Component exists for the same fiscal period but incompatible period type.",
        )
    if required:
        return MetricRecoveryComponentResult(
            component_name=component_name,
            component_status=COMPONENT_MISSING_REQUIRED,
            metric_names=metric_names,
            skip_reason=SKIP_MISSING_REQUIRED_COMPONENT,
            notes="Required component was not found.",
        )
    if zero_if_absent:
        return MetricRecoveryComponentResult(
            component_name=component_name,
            component_status=COMPONENT_ASSUMED_ZERO,
            metric_names=metric_names,
            value_numeric=Decimal("0"),
            coverage_proof=(
                "active period inspected",
                "no approved component metric found",
                "no ambiguous component metric set found",
            ),
            notes="Optional component explicitly allowed to contribute zero when absent.",
        )
    return MetricRecoveryComponentResult(
        component_name=component_name,
        component_status=COMPONENT_MISSING_REQUIRED,
        metric_names=metric_names,
        skip_reason=SKIP_MISSING_REQUIRED_COMPONENT,
        notes="Optional component is not allowed to default to zero.",
    )


def _component_result_from_sources(
    component_name: str,
    status: str,
    metric_names: tuple[str, ...],
    sources: tuple[MetricRecoverySource, ...],
    *,
    skip_reason: str,
    notes: str,
) -> MetricRecoveryComponentResult:
    return MetricRecoveryComponentResult(
        component_name=component_name,
        component_status=status,
        metric_names=metric_names,
        unit=", ".join(sorted({source.unit for source in sources if source.unit})) or None,
        source_metric_ids=_metric_ids(sources),
        source_raw_fact_ids=_raw_fact_ids(sources),
        source_accession_numbers=_accessions(sources),
        skip_reason=skip_reason,
        notes=notes,
    )


def _formula_skip_reason(components: tuple[MetricRecoveryComponentResult, ...]) -> str | None:
    reasons = {component.skip_reason for component in components if component.skip_reason}
    for reason in (
        SKIP_DUPLICATE_COMPONENT_FACTS,
        SKIP_UNIT_MISMATCH,
        SKIP_PERIOD_MISMATCH,
        SKIP_MISSING_REQUIRED_COMPONENT,
    ):
        if reason in reasons:
            return reason
    return None


def _select_failure(evaluations: list[_FormulaEvaluation]) -> _FormulaEvaluation:
    priority = {
        SKIP_DUPLICATE_COMPONENT_FACTS: 0,
        SKIP_UNIT_MISMATCH: 1,
        SKIP_PERIOD_MISMATCH: 2,
        SKIP_MISSING_REQUIRED_COMPONENT: 3,
        None: 99,
    }
    return sorted(evaluations, key=lambda evaluation: priority.get(evaluation.skip_reason, 90))[0]


def _derived_result(period: _PeriodKey, evaluation: _FormulaEvaluation) -> MetricRecoveryResult:
    return MetricRecoveryResult(
        target_metric_name=evaluation.formula.target_metric_name,
        target_xbrl_concept=evaluation.formula.target_xbrl_concept,
        target_recovery_status=TARGET_DERIVED_FROM_COMPONENTS,
        formula_name=evaluation.formula.formula_name,
        formula_version=FORMULA_VERSION,
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_type=period.period_type,
        value_numeric=evaluation.value_numeric,
        unit=evaluation.unit,
        source_metric_ids=_component_metric_ids(evaluation.components),
        source_raw_fact_ids=_component_raw_fact_ids(evaluation.components),
        source_accession_numbers=_component_accessions(evaluation.components),
        assumed_zero_components=tuple(
            component.component_name
            for component in evaluation.components
            if component.component_status == COMPONENT_ASSUMED_ZERO
        ),
        missing_required_components=(),
        review_status=evaluation.review_status,
        skip_reason=None,
        components=evaluation.components,
    )


def _incomplete_result_from_evaluation(
    period: _PeriodKey,
    *,
    target_metric_name: str,
    target_xbrl_concept: str,
    evaluation: _FormulaEvaluation,
) -> MetricRecoveryResult:
    return _incomplete_result(
        period=period,
        target_metric_name=target_metric_name,
        target_xbrl_concept=target_xbrl_concept,
        formula_name=evaluation.formula.formula_name,
        components=evaluation.components,
        skip_reason=evaluation.skip_reason or SKIP_MISSING_REQUIRED_COMPONENT,
        review_status=evaluation.review_status,
    )


def _incomplete_result(
    *,
    period: _PeriodKey,
    target_metric_name: str,
    target_xbrl_concept: str,
    formula_name: str | None,
    components: tuple[MetricRecoveryComponentResult, ...],
    skip_reason: str,
    review_status: str,
    target_status: str = TARGET_DECOMPOSITION_INCOMPLETE,
) -> MetricRecoveryResult:
    return MetricRecoveryResult(
        target_metric_name=target_metric_name,
        target_xbrl_concept=target_xbrl_concept,
        target_recovery_status=target_status,
        formula_name=formula_name,
        formula_version=FORMULA_VERSION,
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_type=period.period_type,
        value_numeric=None,
        unit=None,
        source_metric_ids=_component_metric_ids(components),
        source_raw_fact_ids=_component_raw_fact_ids(components),
        source_accession_numbers=_component_accessions(components),
        assumed_zero_components=tuple(
            component.component_name
            for component in components
            if component.component_status == COMPONENT_ASSUMED_ZERO
        ),
        missing_required_components=tuple(
            component.component_name
            for component in components
            if component.component_status
            in {
                COMPONENT_MISSING_REQUIRED,
                COMPONENT_AMBIGUOUS,
            }
        ),
        review_status=review_status,
        skip_reason=skip_reason,
        components=components,
    )


def _period_matches(metric: MetricRecoverySource, period: _PeriodKey) -> bool:
    return (
        metric.company_id == period.company_id
        and metric.fiscal_year == period.fiscal_year
        and (metric.fiscal_period or "").strip().upper() == period.fiscal_period
        and metric.period_type == period.period_type
    )


def _has_period_mismatch(
    metrics: tuple[MetricRecoverySource, ...],
    *,
    period: _PeriodKey,
    metric_names: tuple[str, ...],
) -> bool:
    return any(
        metric.metric_name in metric_names
        and metric.company_id == period.company_id
        and metric.fiscal_year == period.fiscal_year
        and (metric.fiscal_period or "").strip().upper() == period.fiscal_period
        and metric.period_type != period.period_type
        for metric in metrics
    )


def _component_metric_ids(components: tuple[MetricRecoveryComponentResult, ...]) -> tuple[int, ...]:
    return tuple(sorted({metric_id for component in components for metric_id in component.source_metric_ids}))


def _component_raw_fact_ids(components: tuple[MetricRecoveryComponentResult, ...]) -> tuple[int, ...]:
    return tuple(sorted({raw_fact_id for component in components for raw_fact_id in component.source_raw_fact_ids}))


def _component_accessions(components: tuple[MetricRecoveryComponentResult, ...]) -> tuple[str, ...]:
    return tuple(sorted({accession for component in components for accession in component.source_accession_numbers}))


def _metric_ids(metrics: tuple[MetricRecoverySource, ...]) -> tuple[int, ...]:
    return tuple(sorted(metric.metric_id for metric in metrics if metric.metric_id is not None))


def _raw_fact_ids(metrics: tuple[MetricRecoverySource, ...]) -> tuple[int, ...]:
    return tuple(sorted(metric.raw_fact_id for metric in metrics if metric.raw_fact_id is not None))


def _accessions(metrics: tuple[MetricRecoverySource, ...]) -> tuple[str, ...]:
    return tuple(sorted({metric.accession_number for metric in metrics if metric.accession_number}))
