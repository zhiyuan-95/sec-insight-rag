"""Run company ingestion and print a concise result summary."""

from __future__ import annotations

from pathlib import Path

from src.config import load_settings
from src.ingestion import CompanyIngestionResult, ingest_company

DEFAULT_TICKER = "MSFT"
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
    """Ingest one company and print a brief terminal summary."""
    settings = load_settings(env_file)
    result = ingest_company(ticker, settings)
    print(format_ingestion_report(result))


def format_ingestion_report(result: CompanyIngestionResult, *_: object) -> str:
    """Format a concise ingestion summary while accepting the legacy call shape."""
    return "\n".join(
        (
            "Ingestion summary",
            f"Ticker: {result.ticker} (CIK {result.cik})",
            f"Status: {result.status}",
            f"SEC checked: {_yes_no(result.sec_checked)}",
            f"Active filings: {result.stored_filing_count}",
            f"Raw facts stored this run: {result.stored_fact_count}",
            f"Active base metrics: {result.active_metric_count}",
            f"Active indicators: {result.active_indicator_count}",
            f"Warnings: {len(result.warnings)}",
        )
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
