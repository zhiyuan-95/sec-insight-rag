from dataclasses import replace
from pathlib import Path

import pytest

from src.storage import (
    CompanyIndustryLabelRepository,
    CompanyRecord,
    CompanyRepository,
    IndustryLabelSnapshotConflictError,
    StoredFiscalPeriodIndustryLabelSnapshot,
    connect_sqlite,
)


def test_period_snapshot_round_trips_multiple_labels_and_empty_fallback(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id = _store_company(connection)
        repository = CompanyIndustryLabelRepository(connection)
        multi_label = _snapshot(
            company_id=company_id,
            accession_number="0000000001-24-000001",
            fiscal_year=2023,
            labels=("Energy", "Materials"),
        )
        no_label = _snapshot(
            company_id=company_id,
            accession_number="0000000001-25-000001",
            fiscal_year=2024,
            labels=(),
            label_status="ignored",
        )

        assert repository.insert_period_snapshot(multi_label) is True
        assert repository.insert_period_snapshot(no_label) is True

        assert repository.list_period_snapshots(company_id) == (
            multi_label,
            no_label,
        )
        assert repository.get_period_snapshot(
            company_id=company_id,
            accession_number="0000000001-25-000001",
            fiscal_year=2024,
            fiscal_period="FY",
        ) == no_label


def test_period_snapshot_is_idempotent_but_never_rewritten(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id = _store_company(connection)
        repository = CompanyIndustryLabelRepository(connection)
        original = _snapshot(
            company_id=company_id,
            accession_number="0000000001-24-000001",
            fiscal_year=2023,
            labels=("Energy",),
        )

        assert repository.insert_period_snapshot(original) is True
        assert repository.insert_period_snapshot(original) is False

        with pytest.raises(
            IndustryLabelSnapshotConflictError,
            match="immutable industry-label snapshot",
        ):
            repository.insert_period_snapshot(
                replace(
                    original,
                    assigned_industry_labels=("Energy", "Materials"),
                    assignment_reason="Later business expansion",
                )
            )

        assert repository.list_period_snapshots(company_id) == (original,)


def _store_company(connection) -> int:
    repository = CompanyRepository(connection)
    repository.initialize()
    company = repository.upsert_company(
        CompanyRecord(
            cik="0000000001",
            name="Example Company",
            ticker="EXM",
        )
    )
    assert company.company_id is not None
    return company.company_id


def _snapshot(
    *,
    company_id: int,
    accession_number: str,
    fiscal_year: int,
    labels: tuple[str, ...],
    label_status: str = "assigned",
) -> StoredFiscalPeriodIndustryLabelSnapshot:
    return StoredFiscalPeriodIndustryLabelSnapshot(
        company_id=company_id,
        accession_number=accession_number,
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        assigned_industry_labels=labels,
        assignment_source="gemini_item1_business_classification",
        assignment_reason="Classified from original 10-K Item 1",
        label_status=label_status,
        confidence=0.92,
        evidence=(
            f"Source accession: {accession_number}",
            "Gemini model: gemini-3.1-flash-lite",
        ),
        classifier_version="gemini_item1_business_v1",
    )
