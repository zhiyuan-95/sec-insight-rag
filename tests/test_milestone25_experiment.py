import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

from src.config import Settings
from src.ingestion import FilingMetadata
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


def _load_experiment_module() -> ModuleType:
    module_path = Path("experiments/MS2_5/milestone25_live_sec_inspection.py")
    spec = importlib.util.spec_from_file_location("milestone25_live_sec_inspection", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_milestone25_experiment_presents_first_time_ingestion(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    assert "Milestone 2.5 Plan 2.5 Ingestion Examination" in output
    assert "report output: compact terminal summary" in output
    assert "Initial Setup Ingestion" in output
    assert "Already-Ingested Session Check" in output
    assert "company in system: yes" in output
    assert "update check needed this session: no" in output
    assert "SEC update check performed: no" in output
    assert "SEC result: local data reused; no SEC request made" in output
    assert "new filings ingested this session: none" in output
    assert "company exists after setup" not in output
    assert "Phase 2" not in output
    assert "not_due_reused_local" not in output
    assert "success" not in output.lower()
    assert (tmp_path / "experiment.db").exists()
    assert not (tmp_path / "experiment_report.md").exists()
    assert (tmp_path / "exports" / "companies.csv").exists()
    assert (tmp_path / "exports" / "financial_metrics.csv").exists()


def test_milestone25_experiment_reports_missing_sec_user_agent(
    tmp_path: Path,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    env_file = tmp_path / "config.env"
    env_file.write_text("", encoding="utf-8")

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Execution Warning" in output
    assert "SEC_USER_AGENT is required for live SEC experiment runs" in output
    assert not (tmp_path / "experiment_report.md").exists()


def test_milestone25_write_report_flag_preserves_markdown_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--write-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out
    report = (tmp_path / "experiment_report.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert "saved Markdown report:" in output
    assert "experiment_report.md" in output
    assert "report output: file" in report
    assert "Setup Ingestion" in report
    assert "Already-Ingested Session Check" in report
    assert "Phase 2" not in report


def test_milestone25_prints_report_when_csv_export_is_locked(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    original_export_rows = experiment._export_rows

    def locked_export(rows, path: Path) -> None:
        if path.name == "financial_metrics.csv":
            raise PermissionError("locked by another process")
        original_export_rows(rows, path)

    monkeypatch.setattr(experiment, "_export_rows", locked_export)
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Milestone 2.5 Plan 2.5 Ingestion Examination" in output
    assert "CSV export skipped for financial_metrics" in output
    assert "Initial Setup Ingestion" in output
    assert "Already-Ingested Session Check" in output
    assert "company exists after setup" not in output


def test_milestone25_full_report_flag_prints_detailed_markdown(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--full-report",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "# Milestone 2.5 Live SEC Experiment Report" in output
    assert "Setup Ingestion" in output
    assert "Already-Ingested Session Check" in output
    assert "Compact Traceability Sample" in output
    assert "Phase 2" not in output
    assert not (tmp_path / "experiment_report.md").exists()


def test_milestone25_report_presents_new_filings_when_sec_update_ingests_them(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    experiment = _load_experiment_module()
    calls: list[str] = []
    monkeypatch.setattr(experiment, "ingest_company", _fake_ingest_company_with_update(calls))
    env_file = _env_file(tmp_path)

    exit_code = experiment.main(
        [
            "--ticker",
            "TEST",
            "--env-file",
            str(env_file),
            "--db-path",
            str(tmp_path / "experiment.db"),
            "--report-path",
            str(tmp_path / "experiment_report.md"),
            "--filings-dir",
            str(tmp_path / "filings"),
            "--exports-dir",
            str(tmp_path / "exports"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == ["TEST", "TEST"]
    assert "company in system: yes" in output
    assert "update check needed this session: yes" in output
    assert "SEC update check performed: yes" in output
    assert "SEC result: SEC checked; new active-window filing data ingested" in output
    assert "new filings ingested this session:" in output
    assert "10-Q accession test-10q-new" in output
    assert "next 10-Q check date after session: 2099-01-01" in output


def _fake_ingest_company(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filing_repository.upsert_filings(
                company.company_id,
                [
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10k",
                        form_type="10-K",
                        filing_date=date(2025, 2, 15),
                        fiscal_year=2025,
                        fiscal_period="FY",
                        local_path=settings.stock_filings_base_dir / "test-10k.htm",
                    ),
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q",
                        form_type="10-Q",
                        filing_date=date(2025, 5, 15),
                        fiscal_year=2025,
                        fiscal_period="Q1",
                        local_path=settings.stock_filings_base_dir / "test-10q.htm",
                    ),
                ],
            )
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "reused_local",
            sec_checked=call_number == 1,
            refresh_due_10k=False,
            refresh_due_10q=False,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10k",
                    form="10-K",
                    filing_date="2025-02-15",
                    primary_document="test-10k.htm",
                    document_url="https://example.test/test-10k.htm",
                ),
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q",
                    form="10-Q",
                    filing_date="2025-05-15",
                    primary_document="test-10q.htm",
                    document_url="https://example.test/test-10q.htm",
                ),
            ),
        )

    return ingest


def _fake_ingest_company_with_update(calls: list[str]):
    def ingest(ticker: str, settings: Settings) -> SimpleNamespace:
        calls.append(ticker)
        call_number = len(calls)
        with connect_sqlite(settings.stock_sql_db_path) as connection:
            raw_repository = RawFactRepository(connection)
            company_repository = CompanyRepository(connection)
            filing_repository = FilingRepository(connection)
            metric_repository = FinancialMetricRepository(connection)
            raw_repository.initialize()

            company = company_repository.upsert_company(
                CompanyRecord(
                    cik="0000000001",
                    name="Test Company",
                    ticker=ticker,
                    latest_10k_filing_date=date(2025, 2, 15),
                    latest_10q_filing_date=date(2025, 8, 15) if call_number == 2 else date(2025, 5, 15),
                    next_check_date_10k=date(2099, 1, 1),
                    next_check_date_10q=date(2099, 1, 1) if call_number == 2 else date(2020, 1, 1),
                )
            )
            assert company.company_id is not None

            raw_repository.upsert_facts([_fact(form="10-K", accession_number="test-10k")])
            raw_fact = raw_repository.list_fact_records("0000000001")[0]
            filings = [
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10k",
                    form_type="10-K",
                    filing_date=date(2025, 2, 15),
                    fiscal_year=2025,
                    fiscal_period="FY",
                    local_path=settings.stock_filings_base_dir / "test-10k.htm",
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="test-10q",
                    form_type="10-Q",
                    filing_date=date(2025, 5, 15),
                    fiscal_year=2025,
                    fiscal_period="Q1",
                    local_path=settings.stock_filings_base_dir / "test-10q.htm",
                ),
            ]
            if call_number == 2:
                filings.append(
                    FilingRecord(
                        company_id=company.company_id,
                        accession_number="test-10q-new",
                        form_type="10-Q",
                        filing_date=date(2025, 8, 15),
                        fiscal_year=2025,
                        fiscal_period="Q2",
                        local_path=settings.stock_filings_base_dir / "test-10q-new.htm",
                    )
                )
            filing_repository.upsert_filings(company.company_id, filings)
            filing = filing_repository.get_by_accession("test-10k")
            assert filing is not None
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        filing_id=filing.filing_id,
                        accession_number="test-10k",
                        raw_fact_id=raw_fact.raw_fact_id,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        value_raw=100,
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2025,
                        fiscal_period="FY",
                        filing_date=date(2025, 2, 15),
                    )
                ]
            )

        return SimpleNamespace(
            warnings=(),
            status="initialized" if call_number == 1 else "updated",
            sec_checked=True,
            refresh_due_10k=False,
            refresh_due_10q=call_number == 2,
            filings=(
                FilingMetadata(
                    cik="0000000001",
                    accession_number="test-10q-new" if call_number == 2 else "test-10q",
                    form="10-Q",
                    filing_date="2025-08-15" if call_number == 2 else "2025-05-15",
                    primary_document="test-10q-new.htm" if call_number == 2 else "test-10q.htm",
                    document_url="https://example.test/test-10q-new.htm",
                ),
            ),
        )

    return ingest


def _fact(*, form: str, accession_number: str) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Test Company",
        taxonomy="us-gaap",
        concept="Revenues",
        label="Revenues",
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form=form,
        filed_date=date(2025, 2, 15),
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )


def _env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "config.env"
    env_file.write_text("SEC_USER_AGENT=Test contact@example.com", encoding="utf-8")
    return env_file
