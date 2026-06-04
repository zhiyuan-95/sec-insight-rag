from datetime import date
from decimal import Decimal
from pathlib import Path

from src.processing import NormalizedFact
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FilingRecord,
    FilingRepository,
    FinancialMetric,
    FinancialMetricRepository,
    RawFactRepository,
    connect_sqlite,
)


def test_company_repository_upserts_company_and_refresh_state(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = CompanyRepository(connection)
    repository.initialize()

    first = repository.upsert_company(
        CompanyRecord(
            cik="0000320193",
            name="Apple Inc.",
            ticker="aapl",
            latest_10k_filing_date=date(2025, 10, 31),
            next_check_date_10k=date(2026, 10, 30),
        )
    )
    second = repository.upsert_company(
        CompanyRecord(
            cik="0000320193",
            name="Apple Inc",
            ticker="AAPL",
            latest_10q_filing_date=date(2026, 5, 1),
            next_check_date_10q=date(2026, 7, 31),
        )
    )
    assert first.company_id == second.company_id
    assert second.name == "Apple Inc"
    assert second.ticker == "AAPL"

    repository.update_check_state(
        second.company_id,
        latest_10k_filing_date=date(2026, 10, 30),
        next_check_date_10k=date(2027, 10, 29),
    )

    stored = repository.get_by_ticker("aapl")
    assert stored is not None
    assert stored.latest_10k_filing_date == date(2026, 10, 30)
    assert stored.next_check_date_10k == date(2027, 10, 29)


def test_filing_repository_upserts_and_filters_active_window(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    company_repository = CompanyRepository(connection)
    filing_repository = FilingRepository(connection)
    company_repository.initialize()
    company = company_repository.upsert_company(CompanyRecord(cik="0000320193", name="Apple Inc.", ticker="AAPL"))

    assert company.company_id is not None
    filing_repository.upsert_filings(
        company.company_id,
        [
            FilingRecord(
                company_id=company.company_id,
                accession_number="0000320193-25-000079",
                form_type="10-K",
                filing_date=date(2025, 10, 31),
                fiscal_year=2025,
                fiscal_period="FY",
                local_path=tmp_path / "aapl-20250927.htm",
            ),
            FilingRecord(
                company_id=company.company_id,
                accession_number="0000320193-21-000070",
                form_type="10-K",
                filing_date=date(2021, 10, 29),
                fiscal_year=2021,
                fiscal_period="FY",
                is_active_window=False,
            ),
        ],
    )

    filing_repository.set_active_window(company.company_id, {"0000320193-25-000079"})

    all_filings = filing_repository.list_filings(company.company_id)
    active_filings = filing_repository.list_filings(company.company_id, active_only=True)
    assert len(all_filings) == 2
    assert [filing.accession_number for filing in active_filings] == ["0000320193-25-000079"]
    assert active_filings[0].local_path == tmp_path / "aapl-20250927.htm"


def test_financial_metric_repository_round_trips_traceable_decimal_metrics(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    company_repository = CompanyRepository(connection)
    filing_repository = FilingRepository(connection)
    raw_fact_repository = RawFactRepository(connection)
    metric_repository = FinancialMetricRepository(connection)
    company_repository.initialize()
    company = company_repository.upsert_company(CompanyRecord(cik="0000320193", name="Apple Inc.", ticker="AAPL"))
    assert company.company_id is not None

    raw_fact_repository.upsert_facts([_fact(concept="Revenues", accession_number="0000320193-25-000079")])
    raw_fact = raw_fact_repository.list_fact_records("0000320193")[0]
    filing_repository.upsert_filings(
        company.company_id,
        [
            FilingRecord(
                company_id=company.company_id,
                accession_number="0000320193-25-000079",
                form_type="10-K",
                filing_date=date(2025, 10, 31),
            )
        ],
    )
    filing = filing_repository.get_by_accession("0000320193-25-000079")
    assert filing is not None

    metric_repository.upsert_metrics(
        [
            FinancialMetric(
                company_id=company.company_id,
                filing_id=filing.filing_id,
                accession_number="0000320193-25-000079",
                raw_fact_id=raw_fact.raw_fact_id,
                statement_type="income_statement",
                metric_name="revenue",
                value_numeric=Decimal("391035000000.01"),
                value_raw=391035000000.01,
                unit="USD",
                period_type="duration",
                fiscal_year=2025,
                fiscal_period="FY",
                filing_date=date(2025, 10, 31),
            ),
            FinancialMetric(
                company_id=company.company_id,
                accession_number="0000320193-21-000070",
                statement_type="income_statement",
                metric_name="revenue",
                value_numeric=Decimal("365817000000"),
                value_raw=365817000000,
                unit="USD",
                period_type="duration",
                fiscal_year=2021,
                fiscal_period="FY",
                is_active_window=False,
            ),
        ],
    )

    active_metrics = metric_repository.list_metrics(company.company_id)
    all_metrics = metric_repository.list_metrics(company.company_id, active_only=False)
    assert len(active_metrics) == 1
    assert len(all_metrics) == 2
    assert active_metrics[0].value_numeric == Decimal("391035000000.01")
    assert active_metrics[0].raw_fact_id == raw_fact.raw_fact_id


def _fact(*, concept: str, accession_number: str) -> NormalizedFact:
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
        start_date=date(2024, 9, 29),
        end_date=date(2025, 9, 27),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 10, 31),
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )
