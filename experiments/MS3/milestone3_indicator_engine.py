"""Milestone 3 experiment report for stored derived indicators."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_settings  # noqa: E402
from src.indicators import INDICATOR_DEFINITIONS, indicator_names  # noqa: E402
from src.indicators.models import CALCULATED, SKIPPED, IndicatorResult  # noqa: E402
from src.storage import (  # noqa: E402
    CompanyRecord,
    CompanyRepository,
    FilingRecord,
    FilingRepository,
    FinancialIndicatorRepository,
    FinancialMetric,
    FinancialMetricRepository,
    connect_sqlite,
)

PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass(frozen=True)
class TickerReport:
    """All local evidence needed for one ticker's MS3 report."""

    ticker: str
    company: CompanyRecord | None
    filings: tuple[FilingRecord, ...]
    metrics: tuple[FinancialMetric, ...]
    indicators: tuple[IndicatorResult, ...]
    warning: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    tickers = _parse_tickers(args.ticker)
    settings = load_settings(args.env_file)
    database = Path(args.db_path) if args.db_path else settings.stock_sql_db_path
    active_only = not args.include_inactive

    reports = [
        _load_ticker_report(ticker, database=database, active_only=active_only)
        for ticker in tickers
    ]
    print(format_report(reports, database=database, active_only=active_only))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect stored Milestone 3 derived indicators for one or more tickers.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        required=True,
        help="Ticker to inspect. Can be passed more than once or as a comma-separated list.",
    )
    parser.add_argument("--mode", default="local", choices=["local"], help="Data mode. Only local is supported.")
    parser.add_argument("--env-file", default="config.env", help="Environment file to load settings from.")
    parser.add_argument("--db-path", default=None, help="SQLite database path. Defaults to STOCK_SQL_DB_PATH.")
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include metrics, filings, and indicators outside the active accession window.",
    )
    return parser.parse_args(argv)


def _parse_tickers(raw_values: list[str]) -> tuple[str, ...]:
    tickers: list[str] = []
    for raw_value in raw_values:
        tickers.extend(part.strip().upper() for part in raw_value.split(",") if part.strip())
    if not tickers:
        raise ValueError("At least one ticker is required")
    return tuple(dict.fromkeys(tickers))


def _load_ticker_report(
    ticker: str,
    *,
    database: Path,
    active_only: bool,
) -> TickerReport:
    if not database.exists():
        return TickerReport(
            ticker=ticker,
            company=None,
            filings=(),
            metrics=(),
            indicators=(),
            warning=f"Database does not exist: {database}",
        )

    with connect_sqlite(database) as connection:
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        indicator_repository = FinancialIndicatorRepository(connection)
        indicator_repository.initialize()

        company = company_repository.get_by_ticker(ticker)
        if company is None or company.company_id is None:
            return TickerReport(
                ticker=ticker,
                company=company,
                filings=(),
                metrics=(),
                indicators=(),
                warning=f"No ingested company found for ticker {ticker}.",
            )

        filings = tuple(
            filing_repository.list_filings(
                company.company_id,
                {"10-K", "10-Q"},
                active_only=active_only,
            )
        )
        metrics = tuple(metric_repository.list_metrics(company.company_id, active_only=active_only))
        indicators = tuple(indicator_repository.list_indicators(company.company_id, active_only=active_only))
        warning = None
        if not indicators:
            warning = (
                f"No stored indicators found for {ticker}. "
                "Run company ingestion/update so financial_indicators is populated."
            )
    return TickerReport(
        ticker=ticker,
        company=company,
        filings=filings,
        metrics=metrics,
        indicators=indicators,
        warning=warning,
    )


def format_report(
    reports: list[TickerReport],
    *,
    database: Path,
    active_only: bool,
) -> str:
    lines = [
        "Milestone 3 Experiment: Indicator Engine",
        "",
        "Human Question:",
        "  Can I inspect yearly and quarterly tables for every requested indicator",
        "  within the active accession window for the requested ticker?",
        "",
        "Run Context:",
        f"  mode: local",
        f"  database: {database}",
        f"  active_window_only: {str(active_only).lower()}",
        f"  tickers: {', '.join(report.ticker for report in reports)}",
        "",
    ]
    warnings = [report.warning for report in reports if report.warning]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
        lines.append("")

    lines.extend(_section("Active Accession Window", _active_accession_rows(reports)))
    lines.extend(_section("Input Metric Coverage", _metric_coverage_rows(reports)))
    lines.extend(_section("Indicator Summary", _indicator_summary_rows(reports)))
    lines.extend(_section("Yearly Indicator Table", _indicator_table_rows(reports, period_kind="annual")))
    lines.extend(_section("Quarterly Indicator Table", _indicator_table_rows(reports, period_kind="quarterly")))
    lines.extend(_section("Formula Preview", _formula_rows()))
    lines.extend(_section("Skipped Indicator Cases", _skipped_rows(reports)))
    lines.extend(_section("Source Traceability", _traceability_rows(reports)))
    lines.extend(
        [
            "Artifacts To Inspect:",
            f"  database table: financial_metrics",
            f"  database table: financial_indicators",
            "",
            "Expected Outcome:",
            "  A human can see the active accession window, yearly and quarterly",
            "  indicator tables, skipped values, formulas, and source traceability.",
        ]
    )
    return "\n".join(lines)


def _section(title: str, rows: list[dict[str, object]]) -> list[str]:
    lines = [f"{title}:"]
    if rows:
        lines.extend(_markdown_table(rows))
    else:
        lines.append("  (no rows)")
    lines.append("")
    return lines


def _active_accession_rows(reports: list[TickerReport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report in reports:
        filing_by_accession = {filing.accession_number: filing for filing in report.filings}
        accession_scope: dict[str, dict[str, object]] = {}
        for metric in report.metrics:
            if not metric.accession_number:
                continue
            filing = filing_by_accession.get(metric.accession_number)
            existing = accession_scope.get(metric.accession_number)
            candidate = {
                "ticker": report.ticker,
                "accession_number": metric.accession_number,
                "form": filing.form_type if filing else _inferred_form(metric.fiscal_period),
                "fiscal_year": metric.fiscal_year,
                "fiscal_period": metric.fiscal_period,
                "filing_date": metric.filing_date,
                "active": metric.is_active_window,
            }
            if existing is None or _accession_scope_sort_key(candidate) > _accession_scope_sort_key(existing):
                accession_scope[metric.accession_number] = candidate
        for filing in report.filings:
            accession_scope.setdefault(
                filing.accession_number,
                {
                    "ticker": report.ticker,
                    "accession_number": filing.accession_number,
                    "form": filing.form_type,
                    "fiscal_year": filing.fiscal_year,
                    "fiscal_period": filing.fiscal_period,
                    "filing_date": filing.filing_date,
                    "active": filing.is_active_window,
                },
            )
        for row in sorted(accession_scope.values(), key=_accession_scope_sort_key, reverse=True):
            rows.append(
                row
            )
    return rows


def _metric_coverage_rows(reports: list[TickerReport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report in reports:
        coverage: dict[str, set[tuple[int, str]]] = defaultdict(set)
        for metric in report.metrics:
            if metric.fiscal_year is None or metric.fiscal_period is None:
                continue
            coverage[metric.metric_name].add((metric.fiscal_year, metric.fiscal_period))
        for metric_name in sorted(coverage):
            periods = coverage[metric_name]
            rows.append(
                {
                    "ticker": report.ticker,
                    "metric_name": metric_name,
                    "annual_periods": sum(1 for _, period in periods if period == "FY"),
                    "quarterly_periods": sum(1 for _, period in periods if period != "FY"),
                }
            )
    return rows


def _indicator_summary_rows(reports: list[TickerReport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    names = indicator_names()
    for report in reports:
        grouped: dict[tuple[str, str], list[IndicatorResult]] = defaultdict(list)
        for indicator in report.indicators:
            grouped[(indicator.indicator_name, _period_kind(indicator.fiscal_period))].append(indicator)
        for name in names:
            for period_kind in ("annual", "quarterly"):
                indicators = grouped.get((name, period_kind), [])
                rows.append(
                    {
                        "ticker": report.ticker,
                        "indicator": name,
                        "period_type": period_kind,
                        "periods_calculated": sum(
                            1 for indicator in indicators if indicator.calculation_status == CALCULATED
                        ),
                        "skipped_periods": sum(
                            1 for indicator in indicators if indicator.calculation_status == SKIPPED
                        ),
                        "formula_version": indicators[0].formula_version if indicators else "",
                    }
                )
    return rows


def _indicator_table_rows(
    reports: list[TickerReport],
    *,
    period_kind: str,
) -> list[dict[str, object]]:
    names = indicator_names()
    rows: list[dict[str, object]] = []
    for report in reports:
        by_period = _indicators_by_period(report.indicators)
        periods = [
            period
            for period in _periods_for_report(report)
            if _period_kind(period[1]) == period_kind
        ]
        for fiscal_year, fiscal_period in sorted(periods, key=_period_sort_key, reverse=True):
            row: dict[str, object] = {"ticker": report.ticker, "fiscal_year": fiscal_year}
            if period_kind == "quarterly":
                row["fiscal_period"] = fiscal_period
            for name in names:
                indicator = by_period.get((fiscal_year, fiscal_period, name))
                row[name] = _indicator_cell(indicator)
            rows.append(row)
    return rows


def _formula_rows() -> list[dict[str, object]]:
    return [
        {
            "indicator": definition.indicator_name,
            "formula_version": definition.formula_version,
            "formula": definition.formula_text,
        }
        for definition in INDICATOR_DEFINITIONS
    ]


def _skipped_rows(reports: list[TickerReport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report in reports:
        for indicator in report.indicators:
            if indicator.calculation_status != SKIPPED:
                continue
            rows.append(
                {
                    "ticker": report.ticker,
                    "period": _period_label(indicator.fiscal_year, indicator.fiscal_period),
                    "indicator": indicator.indicator_name,
                    "reason": indicator.skip_reason,
                }
            )
    return rows


def _traceability_rows(reports: list[TickerReport]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for report in reports:
        for indicator in report.indicators:
            if indicator.calculation_status != CALCULATED:
                continue
            rows.append(
                {
                    "ticker": report.ticker,
                    "period": _period_label(indicator.fiscal_year, indicator.fiscal_period),
                    "indicator": indicator.indicator_name,
                    "value": _format_decimal(indicator.value_numeric),
                    "source_metric_ids": _join(indicator.source_metric_ids),
                    "source_raw_fact_ids": _join(indicator.source_raw_fact_ids),
                    "source_accession_numbers": _join(indicator.source_accession_numbers),
                }
            )
    return rows


def _indicators_by_period(
    indicators: tuple[IndicatorResult, ...],
) -> dict[tuple[int, str, str], IndicatorResult]:
    by_period: dict[tuple[int, str, str], IndicatorResult] = {}
    for indicator in indicators:
        if indicator.fiscal_year is None or indicator.fiscal_period is None:
            continue
        key = (indicator.fiscal_year, indicator.fiscal_period, indicator.indicator_name)
        by_period[key] = indicator
    return by_period


def _periods_for_report(report: TickerReport) -> set[tuple[int, str]]:
    periods: set[tuple[int, str]] = set()
    for filing in report.filings:
        if filing.fiscal_year is not None and filing.fiscal_period is not None:
            periods.add((filing.fiscal_year, filing.fiscal_period))
    for indicator in report.indicators:
        if indicator.fiscal_year is not None and indicator.fiscal_period is not None:
            periods.add((indicator.fiscal_year, indicator.fiscal_period))
    for metric in report.metrics:
        if metric.fiscal_year is not None and metric.fiscal_period is not None:
            periods.add((metric.fiscal_year, metric.fiscal_period))
    return periods


def _indicator_cell(indicator: IndicatorResult | None) -> str:
    if indicator is None:
        return ""
    if indicator.calculation_status == SKIPPED:
        return "skipped"
    return _format_decimal(indicator.value_numeric)


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.normalize())


def _join(values: tuple[object, ...]) -> str:
    return ", ".join(str(value) for value in values)


def _period_kind(fiscal_period: str | None) -> str:
    return "annual" if fiscal_period == "FY" else "quarterly"


def _period_label(fiscal_year: int | None, fiscal_period: str | None) -> str:
    if fiscal_year is None:
        return fiscal_period or ""
    if fiscal_period is None:
        return str(fiscal_year)
    return f"{fiscal_year} {fiscal_period}"


def _period_sort_key(period: tuple[int, str]) -> tuple[int, int]:
    fiscal_year, fiscal_period = period
    return fiscal_year, PERIOD_ORDER.get(fiscal_period, 0)


def _accession_scope_sort_key(row: dict[str, object]) -> tuple[int, int, str]:
    fiscal_year = row.get("fiscal_year")
    fiscal_period = str(row.get("fiscal_period") or "")
    accession_number = str(row.get("accession_number") or "")
    return (
        fiscal_year if isinstance(fiscal_year, int) else 0,
        PERIOD_ORDER.get(fiscal_period, 0),
        accession_number,
    )


def _inferred_form(fiscal_period: str | None) -> str:
    return "10-K" if fiscal_period == "FY" else "10-Q"


def _markdown_table(rows: list[dict[str, object]]) -> list[str]:
    headers = list(rows[0])
    normalized_rows = [
        {header: _cell_text(row.get(header)) for header in headers}
        for row in rows
    ]
    widths = {
        header: max(len(header), *(len(row[header]) for row in normalized_rows))
        for header in headers
    }
    lines = [
        "  | " + " | ".join(header.ljust(widths[header]) for header in headers) + " |",
        "  | " + " | ".join("-" * widths[header] for header in headers) + " |",
    ]
    lines.extend(
        "  | " + " | ".join(row[header].ljust(widths[header]) for header in headers) + " |"
        for row in normalized_rows
    )
    return lines


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return _format_decimal(value)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
