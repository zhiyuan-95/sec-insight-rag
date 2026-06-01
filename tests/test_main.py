from datetime import date
from decimal import Decimal
from pathlib import Path

from main import format_ingestion_report
from src.ingestion import CompanyIngestionResult, FilingMetadata
from src.processing import NormalizedFact


def test_format_ingestion_report_summarizes_filings_and_xbrl_content() -> None:
    annual_filing = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-25-000079",
        form="10-K",
        filing_date="2025-10-31",
        primary_document="aapl-20250927.htm",
        document_url="https://example.test/aapl-20250927.htm",
    )
    quarterly_filing = FilingMetadata(
        cik="0000320193",
        accession_number="0000320193-26-000013",
        form="10-Q",
        filing_date="2026-05-01",
        primary_document="aapl-20260328.htm",
        document_url="https://example.test/aapl-20260328.htm",
    )
    result = CompanyIngestionResult(
        ticker="AAPL",
        cik="0000320193",
        filings=(annual_filing, quarterly_filing),
        downloaded_filings=(
            Path("filings/0000320193-25-000079/aapl-20250927.htm"),
            Path("filings/0000320193-26-000013/aapl-20260328.htm"),
        ),
        normalized_fact_count=3,
        stored_fact_count=3,
    )
    facts = [
        _fact(
            concept="Assets",
            fiscal_year=2025,
            fiscal_period="FY",
            form="10-K",
            accession_number="0000320193-25-000079",
        ),
        _fact(
            concept="Assets",
            fiscal_year=2026,
            fiscal_period="Q2",
            form="10-Q",
            accession_number="0000320193-26-000013",
        ),
        _fact(
            concept="Revenues",
            fiscal_year=2026,
            fiscal_period="Q2",
            form="10-Q",
            accession_number="0000320193-26-000013",
        ),
    ]

    report = format_ingestion_report(result, facts)

    assert "10-K annual files: 1 covering 1 fiscal year: FY2025" in report
    assert "10-Q quarterly files: 1 covering 1 fiscal quarter: FY2026 Q2" in report
    assert "Total stored facts for CIK: 3" in report
    assert "XBRL concepts ingested: 2" in report
    assert "XBRL financial facts by statement section:" in report
    assert "Balance sheet: 1 concept, 2 stored facts" in report
    assert "Income statement: 1 concept, 1 stored fact" in report
    assert "us-gaap:Assets: 2 facts; units: USD; periods: FY2026 Q2, FY2025" in report
    assert "us-gaap:Revenues: 1 fact; units: USD; periods: FY2026 Q2" in report
    assert "us-gaap:Assets [USD] (1 fact)" in report
    assert "us-gaap:Revenues [USD] (1 fact)" in report
    assert "0000320193-25-000079 (1 stored XBRL fact, periods: FY2025)" in report
    assert "0000320193-26-000013 (2 stored XBRL facts, periods: FY2026 Q2)" in report


def _fact(
    *,
    concept: str,
    fiscal_year: int,
    fiscal_period: str,
    form: str,
    accession_number: str,
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000320193",
        entity_name="Apple Inc.",
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=date(fiscal_year, 1, 1),
        end_date=date(fiscal_year, 12, 31),
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=date(fiscal_year, 12, 31),
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )
