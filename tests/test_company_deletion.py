import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.config import Settings
from src.ingestion import delete_ingested_company
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


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sec_user_agent="Example contact@example.com",
        stock_sql_db_path=tmp_path / "stock.db",
        stock_filings_base_dir=tmp_path / "filings",
    )


def test_delete_ingested_company_import_does_not_require_settings_package() -> None:
    code = (
        "import builtins; "
        "real = builtins.__import__; "
        "builtins.__import__ = lambda name, *args, **kwargs: "
        "(_ for _ in ()).throw(ModuleNotFoundError('blocked pydantic_settings')) "
        "if name == 'pydantic_settings' else real(name, *args, **kwargs); "
        "from src.ingestion import delete_ingested_company; "
        "print(delete_ingested_company.__name__)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "delete_ingested_company"


def test_delete_ingested_company_removes_registry_data_and_filing_artifacts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    aapl_file = settings.stock_filings_base_dir / "0000320193" / "0000320193-25-000079" / "aapl.htm"
    msft_file = settings.stock_filings_base_dir / "0000789019" / "0000789019-25-000001" / "msft.htm"
    aapl_file.parent.mkdir(parents=True)
    msft_file.parent.mkdir(parents=True)
    aapl_file.write_text("<html>aapl</html>", encoding="utf-8")
    msft_file.write_text("<html>msft</html>", encoding="utf-8")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        raw_fact_repository = RawFactRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_repository.initialize()

        aapl = company_repository.upsert_company(CompanyRecord(cik="0000320193", name="Apple Inc.", ticker="AAPL"))
        msft = company_repository.upsert_company(CompanyRecord(cik="0000789019", name="Microsoft Corp.", ticker="MSFT"))
        assert aapl.company_id is not None
        assert msft.company_id is not None

        raw_fact_repository.upsert_facts(
            [
                _fact(cik="0000320193", concept="Revenues", accession_number="0000320193-25-000079"),
                _fact(cik="0000789019", concept="Assets", accession_number="0000789019-25-000001"),
            ]
        )
        aapl_raw_fact = raw_fact_repository.list_fact_records("0000320193")[0]
        filing_repository.upsert_filings(
            aapl.company_id,
            [
                FilingRecord(
                    company_id=aapl.company_id,
                    accession_number="0000320193-25-000079",
                    form_type="10-K",
                    filing_date=date(2025, 10, 31),
                    local_path=aapl_file,
                )
            ],
        )
        filing_repository.upsert_filings(
            msft.company_id,
            [
                FilingRecord(
                    company_id=msft.company_id,
                    accession_number="0000789019-25-000001",
                    form_type="10-K",
                    filing_date=date(2025, 10, 30),
                    local_path=msft_file,
                )
            ],
        )
        metric_repository.upsert_metrics(
            [
                FinancialMetric(
                    company_id=aapl.company_id,
                    accession_number="0000320193-25-000079",
                    raw_fact_id=aapl_raw_fact.raw_fact_id,
                    statement_type="income_statement",
                    metric_name="revenue",
                    value_numeric=Decimal("100"),
                    value_raw=100,
                    unit="USD",
                    period_type="duration",
                    fiscal_year=2025,
                    fiscal_period="FY",
                )
            ]
        )

    result = delete_ingested_company("aapl", settings)

    assert result.identifier == "AAPL"
    assert result.cik == "0000320193"
    assert result.company_id == aapl.company_id
    assert result.company_found is True
    assert result.message == "Deleted ingested company for identifier 'AAPL' (CIK 0000320193)."
    assert result.metric_rows_deleted == 1
    assert result.filing_rows_deleted == 1
    assert result.raw_fact_rows_deleted == 1
    assert result.company_rows_deleted == 1
    assert result.filing_paths_skipped == ()
    assert any(path.name == "0000320193" for path in result.filing_paths_deleted)
    assert not aapl_file.exists()
    assert not (settings.stock_filings_base_dir / "0000320193").exists()

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        assert CompanyRepository(connection).get_by_cik("0000320193") is None
        assert RawFactRepository(connection).list_facts("0000320193") == []
        assert connection.execute("SELECT COUNT(*) FROM filings WHERE company_id = ?", [aapl.company_id]).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM financial_metrics WHERE company_id = ?", [aapl.company_id]).fetchone()[0] == 0
        assert CompanyRepository(connection).get_by_cik("0000789019") is not None
        assert RawFactRepository(connection).list_facts("0000789019")
        assert msft_file.exists()


def test_delete_ingested_company_reports_missing_cik_and_leaves_orphan_data(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    filing_file = settings.stock_filings_base_dir / "0000320193" / "0000320193-25-000079" / "aapl.htm"
    filing_file.parent.mkdir(parents=True)
    filing_file.write_text("<html>aapl</html>", encoding="utf-8")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_fact_repository = RawFactRepository(connection)
        raw_fact_repository.initialize()
        raw_fact_repository.upsert_facts(
            [_fact(cik="0000320193", concept="Revenues", accession_number="0000320193-25-000079")]
        )

    result = delete_ingested_company("320193", settings)

    assert result.identifier == "320193"
    assert result.cik == "0000320193"
    assert result.company_found is False
    assert result.message == "No ingested company found for identifier '320193' (CIK 0000320193)."
    assert result.raw_fact_rows_deleted == 0
    assert result.company_rows_deleted == 0
    assert result.filing_paths_deleted == ()
    assert filing_file.exists()
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        assert RawFactRepository(connection).list_facts("0000320193")


def test_delete_ingested_company_skips_locked_filing_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    filing_file = settings.stock_filings_base_dir / "0000320193" / "0000320193-25-000079" / "aapl.htm"
    filing_file.parent.mkdir(parents=True)
    filing_file.write_text("<html>aapl</html>", encoding="utf-8")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        raw_fact_repository = RawFactRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(CompanyRecord(cik="0000320193", name="Apple Inc.", ticker="AAPL"))
        assert company.company_id is not None
        raw_fact_repository.upsert_facts(
            [_fact(cik="0000320193", concept="Revenues", accession_number="0000320193-25-000079")]
        )
        filing_repository.upsert_filings(
            company.company_id,
            [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="0000320193-25-000079",
                    form_type="10-K",
                    filing_date=date(2025, 10, 31),
                    local_path=filing_file,
                )
            ],
        )

    def locked_rmtree(path: Path, **kwargs: object) -> None:
        raise PermissionError(f"Locked path: {path}")

    monkeypatch.setattr("src.ingestion.company.shutil.rmtree", locked_rmtree)

    result = delete_ingested_company("320193", settings)

    assert result.cik == "0000320193"
    assert result.company_found is True
    assert result.message == (
        "Deleted ingested company for identifier '320193' (CIK 0000320193), "
        "but some filing artifacts could not be removed."
    )
    assert result.raw_fact_rows_deleted == 1
    assert result.company_rows_deleted == 1
    assert filing_file in result.filing_paths_deleted
    assert result.filing_paths_skipped == (
        (settings.stock_filings_base_dir / "0000320193").resolve(),
    )
    assert not filing_file.exists()


def test_delete_ingested_company_reports_missing_ticker_and_leaves_orphan_data(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    filing_file = settings.stock_filings_base_dir / "0001318605" / "0001318605-25-000001" / "tsla.htm"
    filing_file.parent.mkdir(parents=True)
    filing_file.write_text("<html>tsla</html>", encoding="utf-8")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        raw_fact_repository = RawFactRepository(connection)
        raw_fact_repository.initialize()
        raw_fact_repository.upsert_facts(
            [_fact(cik="0001318605", concept="Revenues", accession_number="0001318605-25-000001")]
        )

    result = delete_ingested_company("tsla", settings)

    assert result.identifier == "TSLA"
    assert result.cik is None
    assert result.company_found is False
    assert result.message == "No ingested company found for identifier 'TSLA'."
    assert result.raw_fact_rows_deleted == 0
    assert result.filing_paths_deleted == ()
    assert filing_file.exists()
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        assert RawFactRepository(connection).list_facts("0001318605")


def test_delete_ingested_company_reports_missing_cik(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with connect_sqlite(settings.stock_sql_db_path) as connection:
        CompanyRepository(connection).initialize()

    result = delete_ingested_company("12345", settings)

    assert result.identifier == "12345"
    assert result.cik == "0000012345"
    assert result.company_found is False
    assert result.message == "No ingested company found for identifier '12345' (CIK 0000012345)."
    assert result.metric_rows_deleted == 0
    assert result.filing_rows_deleted == 0
    assert result.raw_fact_rows_deleted == 0
    assert result.company_rows_deleted == 0
    assert result.filing_paths_deleted == ()
    assert result.filing_paths_skipped == ()


def test_delete_ingested_company_is_idempotent_for_missing_company(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    result = delete_ingested_company("MSFT", settings)

    assert result.identifier == "MSFT"
    assert result.cik is None
    assert result.company_found is False
    assert result.message == "No ingested company found for identifier 'MSFT'."
    assert result.metric_rows_deleted == 0
    assert result.filing_rows_deleted == 0
    assert result.raw_fact_rows_deleted == 0
    assert result.company_rows_deleted == 0
    assert result.filing_paths_deleted == ()
    assert not settings.stock_sql_db_path.exists()


def _fact(*, cik: str, concept: str, accession_number: str) -> NormalizedFact:
    return NormalizedFact(
        cik=cik,
        entity_name="Example Inc.",
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
