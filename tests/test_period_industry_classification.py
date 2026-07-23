from pathlib import Path

from src.analyze.industry_classification import BusinessSectionSource
from src.config.settings import DEFAULT_INDUSTRY_CLASSIFICATION_MODEL
from src.ingestion.industry_labels import (
    FiscalPeriodIndustryClassificationSource,
    classify_and_persist_fiscal_period_industry_labels,
)
from src.processing.company_industry_labels import LABEL_STATUS_NEEDS_REVIEW
from src.storage import (
    CompanyIndustryLabelRepository,
    CompanyRecord,
    CompanyRepository,
    connect_sqlite,
)


def test_original_10k_periods_are_classified_once_and_amendments_are_ignored(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    responses = iter(
        (
            {
                "labels": ["Energy"],
                "confidence": 0.94,
                "reason": "The company produced oil and gas.",
                "evidence_quotes": ["oil and gas production"],
            },
            {
                "labels": ["Energy", "Materials"],
                "confidence": 0.96,
                "reason": "The company expanded into chemical materials.",
                "evidence_quotes": ["chemical materials"],
            },
        )
    )

    def generate_json(prompt: str, schema: type, model: str) -> object:
        calls.append(model)
        return next(responses)

    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id = _store_company(connection)
        repository = CompanyIndustryLabelRepository(connection)
        sources = (
            _source(
                accession_number="0000000001-24-000001",
                form="10-K",
                fiscal_year=2023,
            ),
            _source(
                accession_number="0000000001-24-000002",
                form="10-K/A",
                fiscal_year=2023,
            ),
            _source(
                accession_number="0000000001-25-000001",
                form="10-K",
                fiscal_year=2024,
            ),
        )

        snapshots = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=company_id,
            ticker="EXM",
            cik="0000000001",
            company_name="Example Company",
            sources=sources,
            api_key="fake-key",
            model=DEFAULT_INDUSTRY_CLASSIFICATION_MODEL,
            generate_json=generate_json,
        )

        assert calls == [
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite",
        ]
        assert tuple(
            (
                snapshot.accession_number,
                snapshot.fiscal_year,
                snapshot.assigned_industry_labels,
            )
            for snapshot in snapshots
        ) == (
            ("0000000001-24-000001", 2023, ("Energy",)),
            (
                "0000000001-25-000001",
                2024,
                ("Energy", "Materials"),
            ),
        )

        reused = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=company_id,
            ticker="EXM",
            cik="0000000001",
            company_name="Example Company",
            sources=sources,
            api_key="fake-key",
            model=DEFAULT_INDUSTRY_CLASSIFICATION_MODEL,
            generate_json=lambda prompt, schema, model: (_ for _ in ()).throw(
                AssertionError("immutable snapshots must not be reclassified")
            ),
        )

        assert reused == snapshots


def test_no_label_decision_is_persisted_as_an_empty_snapshot(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id = _store_company(connection)
        repository = CompanyIndustryLabelRepository(connection)

        snapshots = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=company_id,
            ticker="EXM",
            cik="0000000001",
            company_name="Example Company",
            sources=(
                _source(
                    accession_number="0000000001-24-000001",
                    form="10-K",
                    fiscal_year=2023,
                ),
            ),
            api_key="fake-key",
            model=DEFAULT_INDUSTRY_CLASSIFICATION_MODEL,
            generate_json=lambda prompt, schema, model: {
                "labels": [],
                "confidence": 0.88,
                "reason": "No supported hard industry label fits.",
                "evidence_quotes": [],
            },
        )

        assert len(snapshots) == 1
        assert snapshots[0].assigned_industry_labels == ()
        assert snapshots[0].label_status == "ignored"
        assert repository.list_period_snapshots(company_id) == snapshots


def test_existing_source_controlled_assignment_remains_the_fallback(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id = _store_company(
            connection,
            cik="0000789019",
            ticker="MSFT",
            name="Microsoft Corporation",
        )
        repository = CompanyIndustryLabelRepository(connection)

        snapshots = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=company_id,
            ticker="MSFT",
            cik="0000789019",
            company_name="Microsoft Corporation",
            sources=(
                _source(
                    accession_number="0000789019-24-000001",
                    form="10-K",
                    fiscal_year=2023,
                ),
            ),
            api_key="fake-key",
            model=DEFAULT_INDUSTRY_CLASSIFICATION_MODEL,
            generate_json=lambda prompt, schema, model: {
                "labels": ["Information Technology"],
                "confidence": 0.40,
                "reason": "The evidence was too ambiguous.",
                "evidence_quotes": [],
            },
        )

        assert snapshots[0].assigned_industry_labels == (
            "Information Technology",
            "Communication Services",
        )
        assert (
            snapshots[0].assignment_source
            == "manual_source_controlled_registry"
        )


def test_unavailable_gemini_still_persists_fallback_snapshots(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = CompanyIndustryLabelRepository(connection)
        microsoft_id = _store_company(
            connection,
            cik="0000789019",
            ticker="MSFT",
            name="Microsoft Corporation",
        )
        unknown_id = _store_company(
            connection,
            cik="0000000002",
            ticker="NEW",
            name="New Company",
        )

        microsoft = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=microsoft_id,
            ticker="MSFT",
            cik="0000789019",
            company_name="Microsoft Corporation",
            sources=(
                _source(
                    accession_number="0000789019-24-000001",
                    form="10-K",
                    fiscal_year=2023,
                ),
            ),
            api_key=None,
        )
        unknown = classify_and_persist_fiscal_period_industry_labels(
            repository=repository,
            company_id=unknown_id,
            ticker="NEW",
            cik="0000000002",
            company_name="New Company",
            sources=(
                _source(
                    accession_number="0000000002-24-000001",
                    form="10-K",
                    fiscal_year=2023,
                ),
            ),
            api_key=None,
        )

        assert microsoft[0].assigned_industry_labels == (
            "Information Technology",
            "Communication Services",
        )
        assert unknown[0].assigned_industry_labels == ()
        assert unknown[0].label_status == LABEL_STATUS_NEEDS_REVIEW
        assert unknown[0].evidence[-1] == (
            "Gemini classification failure: "
            "GeminiIndustryClassificationUnavailable"
        )


def _store_company(
    connection,
    *,
    cik: str = "0000000001",
    ticker: str = "EXM",
    name: str = "Example Company",
) -> int:
    repository = CompanyRepository(connection)
    repository.initialize()
    company = repository.upsert_company(
        CompanyRecord(
            cik=cik,
            name=name,
            ticker=ticker,
        )
    )
    assert company.company_id is not None
    return company.company_id


def _source(
    *,
    accession_number: str,
    form: str,
    fiscal_year: int,
) -> FiscalPeriodIndustryClassificationSource:
    return FiscalPeriodIndustryClassificationSource(
        form=form,
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        business_section=BusinessSectionSource(
            accession_number=accession_number,
            filing_date=f"{fiscal_year + 1}-02-15",
            local_path=f"filings/{accession_number}.htm",
            text=f"Business description for fiscal year {fiscal_year}.",
        ),
    )
