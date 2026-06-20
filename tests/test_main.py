from pathlib import Path

from main import format_ingestion_report
from src.ingestion import CompanyIngestionResult


def _result() -> CompanyIngestionResult:
    return CompanyIngestionResult(
        ticker="AAPL",
        cik="0000320193",
        filings=(),
        downloaded_filings=(),
        normalized_fact_count=120,
        stored_fact_count=118,
        warnings=("duplicate fact",),
        stored_filing_count=17,
        active_metric_count=42,
        active_indicator_count=31,
        status="updated",
        sec_checked=True,
    )


def test_format_ingestion_report_returns_brief_summary() -> None:
    report = format_ingestion_report(_result())

    assert report.splitlines() == [
        "Ingestion summary",
        "Ticker: AAPL (CIK 0000320193)",
        "Status: updated",
        "SEC checked: yes",
        "Active filings: 17",
        "Raw facts stored this run: 118",
        "Active base metrics: 42",
        "Active indicators: 31",
        "Warnings: 1",
    ]


def test_format_ingestion_report_accepts_legacy_positional_arguments() -> None:
    report = format_ingestion_report(_result(), Path("ignored"), {"ignored": True})

    assert report == format_ingestion_report(_result())
