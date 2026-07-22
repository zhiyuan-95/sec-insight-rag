import json
from datetime import date
from pathlib import Path

import pytest

from src.config import Settings
from src.ingestion import (
    CompanyIngestionResult,
    FilingMetadata,
    SecConfigurationError,
    SecIngestionError,
    TickerMapping,
    ingest_company,
)
from src.ingestion import company as company_module
from src.analyze.industry_classification import (
    GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
    GEMINI_INDUSTRY_CLASSIFIER_VERSION,
)
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    LABEL_STATUS_ASSIGNED,
)
from src.retrieval.models import ParsedFiling, ParsedSection
from src.storage import (
    CompanyRecord,
    CompanyIndustryLabelRepository,
    CompanyRepository,
    FilingRecord,
    FilingRepository,
    FinancialMetricRepository,
    RawFactRepository,
    StoredCompanyIndustryLabel,
    connect_sqlite,
)


def _settings(tmp_path: Path, sec_user_agent: str | None = "Example contact@example.com") -> Settings:
    return Settings(
        sec_user_agent=sec_user_agent,
        stock_sql_db_path=tmp_path / "stock.db",
        stock_filings_base_dir=tmp_path / "filings",
    )


def test_ingest_company_orchestrates_sec_processing_and_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))
    companyfacts = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))
    call_order: list[str] = []

    def load_ticker_mapping(client) -> dict[str, TickerMapping]:
        call_order.append("load_ticker_mapping")
        return {"AAPL": TickerMapping(ticker="AAPL", cik="0000320193", title="Apple Inc.")}

    def get_company_submissions(client, cik: str) -> dict:
        call_order.append("get_company_submissions")
        assert cik == "0000320193"
        return submissions

    def get_companyfacts(client, cik: str) -> dict:
        call_order.append("get_companyfacts")
        assert cik == "0000320193"
        return companyfacts

    def download_filing_document(client, filing: FilingMetadata, base_dir: Path) -> Path:
        call_order.append(f"download:{filing.form}")
        path = base_dir / filing.cik / filing.accession_number / filing.primary_document
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>filing</html>", encoding="utf-8")
        return path

    monkeypatch.setattr(company_module, "load_ticker_mapping", load_ticker_mapping)
    monkeypatch.setattr(company_module, "get_company_submissions", get_company_submissions)
    monkeypatch.setattr(company_module, "get_companyfacts", get_companyfacts)
    monkeypatch.setattr(company_module, "download_filing_document", download_filing_document)

    result = ingest_company(" aapl ", _settings(tmp_path))

    assert isinstance(result, CompanyIngestionResult)
    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert {filing.form for filing in result.filings} == {"10-K", "10-Q"}
    assert len(result.downloaded_filings) == 2
    assert result.normalized_fact_count == 6
    assert result.stored_fact_count == 6
    assert result.company_id is not None
    assert result.stored_filing_count == 2
    assert result.stored_metric_count == 2
    assert result.active_metric_count == 2
    assert result.status == "initialized"
    assert result.sec_checked is True
    assert result.warnings == (
        "Normalized facts include quality flag: ambiguous_unit",
        "Normalized facts include quality flag: duplicate_fact",
        "Normalized facts include quality flag: unsupported_form",
    )
    assert call_order[:3] == [
        "load_ticker_mapping",
        "get_company_submissions",
        "get_companyfacts",
    ]

    with connect_sqlite(tmp_path / "stock.db") as connection:
        stored = RawFactRepository(connection).list_facts("0000320193")
        company = CompanyRepository(connection).get_by_cik("0000320193")
        assert company is not None
        assert company.company_id is not None
        filings = FilingRepository(connection).list_filings(company.company_id)
        metrics = FinancialMetricRepository(connection).list_metrics(company.company_id)

    assert len(stored) == 5
    assert {fact.concept for fact in stored} == {"Assets", "Revenues"}
    assert {fact.form for fact in stored} == {"10-K", "10-Q", "8-K"}
    assert company.name == "Apple Inc."
    assert company.latest_10k_filing_date == date(2025, 10, 31)
    assert company.latest_10q_filing_date == date(2025, 8, 1)
    assert company.next_check_date_10k == date(2026, 10, 30)
    assert company.next_check_date_10q == date(2026, 1, 30)
    assert {filing.accession_number for filing in filings} == {
        "0000320193-25-000073",
        "0000320193-25-000079",
    }
    assert all(filing.is_active_window for filing in filings)
    assert len(metrics) == 2
    assert {metric.statement_type for metric in metrics} == {"income_statement"}
    assert {metric.metric_name for metric in metrics} == {"revenue"}
    assert {metric.accession_number for metric in metrics} == {
        "0000320193-25-000073",
        "0000320193-25-000079",
    }
    assert all(metric.raw_fact_id is not None for metric in metrics)


def test_ingest_company_persists_gemini_industry_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submissions = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))
    companyfacts = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))
    classified: list[str] = []

    def load_ticker_mapping(client) -> dict[str, TickerMapping]:
        return {"AAPL": TickerMapping(ticker="AAPL", cik="0000320193", title="Apple Inc.")}

    def get_company_submissions(client, cik: str) -> dict:
        return submissions

    def get_companyfacts(client, cik: str) -> dict:
        return companyfacts

    def download_filing_document(client, filing: FilingMetadata, base_dir: Path) -> Path:
        path = base_dir / filing.cik / filing.accession_number / filing.primary_document
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>filing</html>", encoding="utf-8")
        return path

    def parse_filing_html(path: Path, form_type: str) -> ParsedFiling:
        assert form_type == "10-K"
        return ParsedFiling(
            source_sha256="abc",
            sections=(
                ParsedSection(
                    name="business",
                    title="Item 1. Business",
                    order=10,
                    text="Apple designs consumer devices, software, services, and related platforms.",
                ),
            ),
        )

    def classify_company_industry_labels(**kwargs) -> CompanyIndustryLabelAssignment:
        business_section = kwargs["business_section"]
        classified.append(business_section.accession_number)
        assert business_section.text.startswith("Apple designs consumer devices")
        return CompanyIndustryLabelAssignment(
            ticker="AAPL",
            cik="0000320193",
            assigned_industry_labels=("Information Technology",),
            assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
            assignment_reason="Apple reports devices, software, and services.",
            supporting_evidence=(
                "Source accession: 0000320193-25-000079",
                "Source section: 10-K Item 1. Business",
            ),
            reviewed_at="",
            label_status=LABEL_STATUS_ASSIGNED,
            confidence=0.93,
            classifier_version=GEMINI_INDUSTRY_CLASSIFIER_VERSION,
        )

    monkeypatch.setattr(company_module, "load_ticker_mapping", load_ticker_mapping)
    monkeypatch.setattr(company_module, "get_company_submissions", get_company_submissions)
    monkeypatch.setattr(company_module, "get_companyfacts", get_companyfacts)
    monkeypatch.setattr(company_module, "download_filing_document", download_filing_document)
    monkeypatch.setattr(company_module, "parse_filing_html", parse_filing_html)
    monkeypatch.setattr(
        company_module,
        "classify_company_industry_labels",
        classify_company_industry_labels,
    )

    settings = Settings(
        sec_user_agent="Example contact@example.com",
        stock_sql_db_path=tmp_path / "stock.db",
        stock_filings_base_dir=tmp_path / "filings",
        gemini_api_key="fake-key",
    )
    result = ingest_company("AAPL", settings)

    assert result.industry_label_count == 1
    assert classified == ["0000320193-25-000079"]
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company = CompanyRepository(connection).get_by_cik("0000320193")
        assert company is not None
        assert company.company_id is not None
        labels = CompanyIndustryLabelRepository(connection).list_labels(company.company_id)

    assert len(labels) == 1
    assert labels[0].industry_label == "Information Technology"
    assert labels[0].assignment_source == GEMINI_INDUSTRY_ASSIGNMENT_SOURCE
    assert labels[0].confidence == 0.93
    assert labels[0].classifier_version == GEMINI_INDUSTRY_CLASSIFIER_VERSION
    assert labels[0].evidence == (
        "Source accession: 0000320193-25-000079",
        "Source section: 10-K Item 1. Business",
    )


def test_gemini_industry_classification_reuses_same_10k_accession() -> None:
    stored_label = StoredCompanyIndustryLabel(
        company_id=1,
        industry_label="Information Technology",
        assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
        assignment_reason="classified from Item 1",
        classifier_version=GEMINI_INDUSTRY_CLASSIFIER_VERSION,
        evidence=("Source accession: 0000320193-25-000079",),
    )

    assert (
        company_module._industry_classification_due(
            (stored_label,),
            "0000320193-25-000079",
        )
        is False
    )
    assert (
        company_module._industry_classification_due(
            (stored_label,),
            "0000320193-26-000080",
        )
        is True
    )


def test_source_controlled_labels_remain_due_for_gemini_classification() -> None:
    stored_label = StoredCompanyIndustryLabel(
        company_id=1,
        industry_label="Information Technology",
        assignment_source="manual_source_controlled_registry",
        assignment_reason="seed label",
        classifier_version="source_controlled_registry_v1",
        evidence=("SEC SIC 7372: Services-Prepackaged Software",),
    )

    assert (
        company_module._industry_classification_due(
            (stored_label,),
            "0000320193-25-000079",
        )
        is True
    )


def test_ingest_company_rejects_missing_sec_user_agent(tmp_path: Path) -> None:
    with pytest.raises(SecConfigurationError):
        ingest_company("AAPL", _settings(tmp_path, sec_user_agent=None))


def test_ingest_company_reuses_local_company_when_refresh_is_not_due(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path, sec_user_agent=None)
    _store_local_company(
        settings,
        next_check_date_10k=date(2099, 10, 31),
        next_check_date_10q=date(2099, 7, 31),
    )

    def fail_load_ticker_mapping(client) -> dict[str, TickerMapping]:
        raise AssertionError("SEC ticker mapping should not be loaded")

    monkeypatch.setattr(company_module, "load_ticker_mapping", fail_load_ticker_mapping)

    result = ingest_company("aapl", settings)

    assert result.status == "reused_local"
    assert result.sec_checked is False
    assert result.refresh_due_10k is False
    assert result.refresh_due_10q is False
    assert result.normalized_fact_count == 0
    assert result.stored_fact_count == 0
    assert result.stored_filing_count == 2
    assert len(result.filings) == 2
    assert all(path is not None for path in result.downloaded_filings)


def test_ingest_company_uses_local_company_when_due_refresh_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _store_local_company(
        settings,
        next_check_date_10k=date(2020, 1, 1),
        next_check_date_10q=date(2020, 1, 1),
    )

    def fail_load_ticker_mapping(client) -> dict[str, TickerMapping]:
        raise SecIngestionError("SEC unavailable")

    monkeypatch.setattr(company_module, "load_ticker_mapping", fail_load_ticker_mapping)

    result = ingest_company("AAPL", settings)

    assert result.status == "refresh_failed_using_local_data"
    assert result.sec_checked is True
    assert result.refresh_due_10k is True
    assert result.refresh_due_10q is True
    assert result.normalized_fact_count == 0
    assert result.warnings == ("SEC refresh failed; using existing local data: SEC unavailable",)


def test_ingest_company_due_refresh_without_new_filings_advances_check_dates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    _store_local_company(
        settings,
        next_check_date_10k=date(2020, 1, 1),
        next_check_date_10q=date(2020, 1, 1),
    )
    submissions = json.loads(Path("data/fixtures/sec_submissions_sample.json").read_text(encoding="utf-8"))
    companyfacts = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))

    def load_ticker_mapping(client) -> dict[str, TickerMapping]:
        return {"AAPL": TickerMapping(ticker="AAPL", cik="0000320193", title="Apple Inc.")}

    def get_company_submissions(client, cik: str) -> dict:
        return submissions

    def get_companyfacts(client, cik: str) -> dict:
        return companyfacts

    def fail_download_filing_document(client, filing: FilingMetadata, base_dir: Path) -> Path:
        raise AssertionError("Existing active filing documents should be reused")

    monkeypatch.setattr(company_module, "load_ticker_mapping", load_ticker_mapping)
    monkeypatch.setattr(company_module, "get_company_submissions", get_company_submissions)
    monkeypatch.setattr(company_module, "get_companyfacts", get_companyfacts)
    monkeypatch.setattr(company_module, "download_filing_document", fail_download_filing_document)

    result = ingest_company("AAPL", settings)

    assert result.status == "checked_no_update"
    assert result.normalized_fact_count == 6
    assert result.stored_fact_count == 6
    assert result.refresh_due_10k is True
    assert result.refresh_due_10q is True

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company = CompanyRepository(connection).get_by_cik("0000320193")

    assert company is not None
    assert company.next_check_date_10k is not None
    assert company.next_check_date_10q is not None
    assert company.next_check_date_10k > date.today()
    assert company.next_check_date_10q > date.today()


def _store_local_company(
    settings: Settings,
    *,
    next_check_date_10k: date,
    next_check_date_10q: date,
) -> None:
    annual_path = (
        settings.stock_filings_base_dir
        / "0000320193"
        / "0000320193-25-000079"
        / "aapl-20250927.htm"
    )
    quarterly_path = (
        settings.stock_filings_base_dir
        / "0000320193"
        / "0000320193-25-000073"
        / "aapl-20250628.htm"
    )
    annual_path.parent.mkdir(parents=True, exist_ok=True)
    quarterly_path.parent.mkdir(parents=True, exist_ok=True)
    annual_path.write_text("<html>10-K</html>", encoding="utf-8")
    quarterly_path.write_text("<html>10-Q</html>", encoding="utf-8")

    with connect_sqlite(settings.stock_sql_db_path) as connection:
        company_repository = CompanyRepository(connection)
        filing_repository = FilingRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(
                cik="0000320193",
                name="Apple Inc.",
                ticker="AAPL",
                latest_10k_filing_date=date(2025, 10, 31),
                latest_10q_filing_date=date(2025, 8, 1),
                next_check_date_10k=next_check_date_10k,
                next_check_date_10q=next_check_date_10q,
            )
        )
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
                    document_url="https://example.test/aapl-20250927.htm",
                    local_path=annual_path,
                ),
                FilingRecord(
                    company_id=company.company_id,
                    accession_number="0000320193-25-000073",
                    form_type="10-Q",
                    filing_date=date(2025, 8, 1),
                    fiscal_year=2025,
                    fiscal_period="Q3",
                    document_url="https://example.test/aapl-20250628.htm",
                    local_path=quarterly_path,
                ),
            ],
        )
