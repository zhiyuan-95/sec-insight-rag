"""Run company ingestion and print a concise SEC/XBRL ingestion report."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from src.config import Settings, load_settings
from src.ingestion import CompanyIngestionResult, FilingMetadata, ingest_company
from src.processing import NormalizedFact
from src.storage import CompanyRepository, FinancialMetric, FinancialMetricRepository, RawFactRepository, connect_sqlite

DEFAULT_TICKER = "AAPL"
PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}
FINANCIAL_STATEMENT_BY_CONCEPT = {
    "Assets": "Balance sheet",
    "AssetsCurrent": "Balance sheet",
    "CashAndCashEquivalentsAtCarryingValue": "Balance sheet",
    "Liabilities": "Balance sheet",
    "LiabilitiesCurrent": "Balance sheet",
    "StockholdersEquity": "Balance sheet",
    "CostOfRevenue": "Income statement",
    "GrossProfit": "Income statement",
    "NetIncomeLoss": "Income statement",
    "OperatingIncomeLoss": "Income statement",
    "ResearchAndDevelopmentExpense": "Income statement",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Income statement",
    "Revenues": "Income statement",
    "MarketableSecuritiesCurrent": "Balance sheet",
    "EarningsPerShareBasic": "EPS and shares",
    "NetCashProvidedByUsedInOperatingActivities": "Cash flow statement",
    "NetCashProvidedByUsedInInvestingActivities": "Cash flow statement",
    "PaymentsToAcquirePropertyPlantAndEquipment": "Cash flow statement",
    "OtherComprehensiveIncomeLossNetOfTax": "Other comprehensive income",
}
FINANCIAL_STATEMENT_ORDER = (
    "Income statement",
    "Balance sheet",
    "Cash flow statement",
    "EPS and shares",
    "Other comprehensive income",
    "Unmapped financial facts",
)


def main(ticker: str = DEFAULT_TICKER, env_file: str | Path = "config.env") -> None:
    """Ingest SEC filings and XBRL facts for one ticker, then print what was stored."""
    settings = load_settings(env_file)
    result = ingest_company(ticker, settings)
    stored_facts = load_stored_facts(settings, result.cik)
    stored_metrics = load_stored_metrics(settings, result.cik)

    print(format_ingestion_report(result, stored_facts, stored_metrics))


def load_stored_facts(settings: Settings, cik: str) -> list[NormalizedFact]:
    """Load normalized XBRL facts stored by the ingestion workflow."""
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        repository = RawFactRepository(connection)
        repository.initialize()
        return repository.list_facts(cik)


def load_stored_metrics(settings: Settings, cik: str) -> list[FinancialMetric]:
    """Load active base financial metrics stored by the ingestion workflow."""
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        company_repository.initialize()
        company = company_repository.get_by_cik(cik)
        if company is None or company.company_id is None:
            return []
        return FinancialMetricRepository(connection).list_metrics(company.company_id)


def format_ingestion_report(
    result: CompanyIngestionResult,
    facts: list[NormalizedFact],
    metrics: list[FinancialMetric] | None = None,
) -> str:
    """Format a human-readable report for downloaded filings and stored XBRL facts."""
    filing_paths = dict(zip(result.filings, result.downloaded_filings, strict=False))
    facts_by_accession = _facts_by_accession(facts)
    filings_by_form = _filings_by_form(result.filings)

    lines = [
        f"Ticker: {result.ticker}",
        f"CIK: {result.cik}",
        f"Run status: {result.status}",
        f"SEC checked: {_format_bool(result.sec_checked)}",
        f"Refresh due: 10-K={_format_optional_bool(result.refresh_due_10k)}, "
        f"10-Q={_format_optional_bool(result.refresh_due_10q)}",
        "",
        "Downloaded SEC filing files:",
    ]
    lines.extend(_format_download_summary(filings_by_form, filing_paths, facts_by_accession))
    lines.extend(
        [
            "",
            "XBRL companyfacts ingested into SQLite:",
            f"- Normalized facts this run: {result.normalized_fact_count}",
            f"- Stored facts this run: {result.stored_fact_count}",
            f"- Total stored facts for CIK: {len(facts)}",
        ]
    )
    lines.extend(_format_xbrl_period_summary(facts))
    lines.extend(_format_concept_summary(facts))
    lines.extend(["", "XBRL financial facts by statement section:"])
    lines.extend(_format_financial_statement_fact_summary(facts))
    if metrics is not None:
        lines.extend(["", "Base financial metrics mapped for active analysis window:"])
        lines.extend(_format_financial_metric_summary(metrics))
    lines.extend(["", "Downloaded filing to XBRL fact mapping:"])
    lines.extend(_format_filing_fact_mapping(result.filings, filing_paths, facts_by_accession))

    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result.warnings)

    return "\n".join(lines)


def _filings_by_form(filings: tuple[FilingMetadata, ...]) -> dict[str, list[FilingMetadata]]:
    grouped: dict[str, list[FilingMetadata]] = defaultdict(list)
    for filing in filings:
        grouped[filing.form].append(filing)
    return dict(grouped)


def _facts_by_accession(facts: list[NormalizedFact]) -> dict[str, list[NormalizedFact]]:
    grouped: dict[str, list[NormalizedFact]] = defaultdict(list)
    for fact in facts:
        if fact.accession_number:
            grouped[fact.accession_number].append(fact)
    return dict(grouped)


def _format_download_summary(
    filings_by_form: dict[str, list[FilingMetadata]],
    filing_paths: dict[FilingMetadata, Path | None],
    facts_by_accession: dict[str, list[NormalizedFact]],
) -> list[str]:
    lines: list[str] = []
    for form, label in (("10-K", "annual"), ("10-Q", "quarterly")):
        filings = filings_by_form.get(form, [])
        periods = _periods_for_filings(filings, facts_by_accession)
        period_word = "fiscal year" if form == "10-K" else "fiscal quarter"
        lines.append(
            f"- {form} {label} files: {len(filings)} covering {len(periods)} "
            f"{_pluralize(period_word, len(periods))}: {_format_list(periods)}"
        )
        for filing in sorted(filings, key=lambda item: item.filing_date, reverse=True):
            path = filing_paths.get(filing)
            lines.append(f"  - {filing.filing_date} {filing.accession_number}: {path or 'not downloaded'}")
    return lines


def _format_xbrl_period_summary(facts: list[NormalizedFact]) -> list[str]:
    lines: list[str] = []
    for form, label in (("10-K", "annual"), ("10-Q", "quarterly")):
        form_facts = [fact for fact in facts if fact.form == form]
        periods = _periods_for_facts(form_facts)
        period_word = "fiscal year" if form == "10-K" else "fiscal quarter"
        lines.append(
            f"- {form} XBRL {label} periods in storage: {len(periods)} "
            f"{_pluralize(period_word, len(periods))}: {_format_list(periods, limit=12)}"
        )
    return lines


def _format_concept_summary(facts: list[NormalizedFact]) -> list[str]:
    concepts = sorted({f"{fact.taxonomy}:{fact.concept}" for fact in facts})
    return [
        f"- XBRL concepts ingested: {len(concepts)}",
        f"  {_format_list(concepts, limit=20)}",
    ]


def _format_financial_statement_fact_summary(facts: list[NormalizedFact]) -> list[str]:
    if not facts:
        return ["- No XBRL financial facts found in storage."]

    facts_by_statement: dict[str, list[NormalizedFact]] = defaultdict(list)
    for fact in facts:
        statement = FINANCIAL_STATEMENT_BY_CONCEPT.get(fact.concept, "Unmapped financial facts")
        facts_by_statement[statement].append(fact)

    lines: list[str] = []
    for statement in FINANCIAL_STATEMENT_ORDER:
        statement_facts = facts_by_statement.get(statement, [])
        if not statement_facts:
            continue
        concept_count = len({(fact.taxonomy, fact.concept) for fact in statement_facts})
        fact_count = len(statement_facts)
        lines.append(
            f"- {statement}: {concept_count} {_pluralize('concept', concept_count)}, "
            f"{fact_count} {_pluralize('stored fact', fact_count)}"
        )
        lines.extend(_format_statement_concepts(statement_facts))
    return lines


def _format_financial_metric_summary(metrics: list[FinancialMetric]) -> list[str]:
    if not metrics:
        return ["- No active base financial metrics found."]

    metrics_by_statement: dict[str, list[FinancialMetric]] = defaultdict(list)
    for metric in metrics:
        metrics_by_statement[metric.statement_type].append(metric)

    lines: list[str] = []
    for statement, statement_metrics in sorted(metrics_by_statement.items()):
        metric_names = sorted({metric.metric_name for metric in statement_metrics})
        lines.append(
            f"- {_metric_statement_label(statement)}: {len(metric_names)} "
            f"{_pluralize('metric name', len(metric_names))}, "
            f"{len(statement_metrics)} {_pluralize('metric value', len(statement_metrics))}"
        )
        for metric_name in metric_names:
            metric_values = [metric for metric in statement_metrics if metric.metric_name == metric_name]
            units = sorted({metric.unit for metric in metric_values})
            periods = _periods_for_metrics(metric_values)
            lines.append(
                f"  - {metric_name}: {len(metric_values)} {_pluralize('value', len(metric_values))}; "
                f"units: {_format_list(units)}; periods: {_format_list(periods, limit=8)}"
            )
    return lines


def _format_statement_concepts(facts: list[NormalizedFact]) -> list[str]:
    facts_by_concept: dict[tuple[str, str], list[NormalizedFact]] = defaultdict(list)
    for fact in facts:
        facts_by_concept[(fact.taxonomy, fact.concept)].append(fact)

    lines: list[str] = []
    for (taxonomy, concept), concept_facts in sorted(facts_by_concept.items()):
        units = sorted({fact.unit for fact in concept_facts})
        periods = _periods_for_facts(concept_facts)
        lines.append(
            f"  - {taxonomy}:{concept}: {len(concept_facts)} "
            f"{_pluralize('fact', len(concept_facts))}; units: {_format_list(units)}; "
            f"periods: {_format_list(periods, limit=8)}"
        )
    return lines


def _format_filing_fact_mapping(
    filings: tuple[FilingMetadata, ...],
    filing_paths: dict[FilingMetadata, Path | None],
    facts_by_accession: dict[str, list[NormalizedFact]],
) -> list[str]:
    if not filings:
        return ["- No downloaded filings were returned by ingestion."]

    lines: list[str] = []
    for filing in sorted(filings, key=lambda item: (item.form, item.filing_date), reverse=True):
        filing_facts = facts_by_accession.get(filing.accession_number, [])
        path = filing_paths.get(filing)
        periods = _periods_for_facts(filing_facts)
        fact_label = _pluralize("stored XBRL fact", len(filing_facts))
        lines.append(
            f"- {filing.form} {filing.filing_date} {filing.accession_number}"
            f" ({len(filing_facts)} {fact_label}, periods: {_format_list(periods)}):"
        )
        lines.append(f"  file: {path or 'not downloaded'}")
        lines.extend(_format_filing_concepts(filing_facts))
    return lines


def _format_filing_concepts(facts: list[NormalizedFact]) -> list[str]:
    if not facts:
        return ["  concepts: none found for this accession number"]

    counts = Counter((fact.taxonomy, fact.concept, fact.unit) for fact in facts)
    concepts = [
        f"{taxonomy}:{concept} [{unit}] ({count} {_pluralize('fact', count)})"
        for (taxonomy, concept, unit), count in sorted(counts.items())
    ]
    return [f"  concepts: {_format_list(concepts, limit=14)}"]


def _periods_for_filings(
    filings: list[FilingMetadata],
    facts_by_accession: dict[str, list[NormalizedFact]],
) -> list[str]:
    periods: set[tuple[int | None, str | None, str]] = set()
    for filing in filings:
        filing_facts = facts_by_accession.get(filing.accession_number, [])
        periods.update(_period_keys(filing_facts))
        if not filing_facts:
            periods.add((None, None, filing.filing_date))
    return _format_period_keys(periods)


def _periods_for_facts(facts: list[NormalizedFact]) -> list[str]:
    return _format_period_keys(_period_keys(facts))


def _periods_for_metrics(metrics: list[FinancialMetric]) -> list[str]:
    return _format_period_keys(
        {
            (metric.fiscal_year, metric.fiscal_period, metric.end_date.isoformat() if metric.end_date else "")
            for metric in metrics
        }
    )


def _period_keys(facts: list[NormalizedFact]) -> set[tuple[int | None, str | None, str]]:
    keys: set[tuple[int | None, str | None, str]] = set()
    for fact in facts:
        if fact.fiscal_year is None and fact.fiscal_period is None:
            if fact.end_date is not None:
                keys.add((None, None, fact.end_date.isoformat()))
            continue
        keys.add((fact.fiscal_year, fact.fiscal_period, ""))
    return keys


def _format_period_keys(periods: set[tuple[int | None, str | None, str]]) -> list[str]:
    sorted_periods = sorted(
        periods,
        key=lambda item: (
            item[0] or 0,
            PERIOD_ORDER.get(item[1] or "", 0),
            item[2],
        ),
        reverse=True,
    )
    return [_format_period(fiscal_year, fiscal_period, fallback) for fiscal_year, fiscal_period, fallback in sorted_periods]


def _format_period(fiscal_year: int | None, fiscal_period: str | None, fallback: str) -> str:
    if fiscal_year is None:
        return fallback or "unknown period"
    if fiscal_period and fiscal_period != "FY":
        return f"FY{fiscal_year} {fiscal_period}"
    return f"FY{fiscal_year}"


def _format_list(values: list[str], limit: int | None = None) -> str:
    if not values:
        return "none"
    if limit is None or len(values) <= limit:
        return ", ".join(values)
    shown = values[:limit]
    return f"{', '.join(shown)} ... (+{len(values) - limit} more)"


def _pluralize(label: str, count: int) -> str:
    return label if count == 1 else f"{label}s"


def _metric_statement_label(statement_type: str) -> str:
    return statement_type.replace("_", " ").title()


def _format_bool(value: bool) -> str:
    return "yes" if value else "no"


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return _format_bool(value)
