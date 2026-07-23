from datetime import date
from decimal import Decimal
from pathlib import Path

from src.processing import NormalizedFact, ShadowMappingCandidate
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FinancialMetricRepository,
    MappingShadowCandidateRepository,
    RawFactRepository,
    connect_sqlite,
)


def test_shadow_candidate_repository_round_trips_evidence_without_creating_metric(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_repository = CompanyRepository(connection)
        raw_fact_repository = RawFactRepository(connection)
        shadow_repository = MappingShadowCandidateRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(
                cik="0000000001",
                name="Example Company",
                ticker="EXM",
            )
        )
        assert company.company_id is not None
        raw_fact_repository.upsert_facts([_fact()])
        raw_fact = raw_fact_repository.list_fact_records("0000000001")[0]

        stored_count = shadow_repository.upsert_period_candidates(
            company_id=company.company_id,
            fiscal_year=2025,
            fiscal_period="FY",
            candidates=(
                ShadowMappingCandidate(
                    raw_fact_id=raw_fact.raw_fact_id,
                    taxonomy="custom",
                    concept="CustomerRevenueGross",
                    metric_name="revenue",
                    statement_type="income_statement",
                    score=0.75,
                    match_method="arelle_lexical_shadow_v1",
                    evidence={
                        "candidate_is_authoritative": False,
                        "observed_label": "Customer revenue gross",
                    },
                ),
            ),
        )

        candidates = shadow_repository.list_for_period(
            company_id=company.company_id,
            fiscal_year=2025,
            fiscal_period="FY",
        )
        metrics = metric_repository.list_metrics(
            company.company_id,
            active_only=False,
        )

    assert stored_count == 1
    assert len(candidates) == 1
    assert candidates[0].raw_fact_id == raw_fact.raw_fact_id
    assert candidates[0].metric_name == "revenue"
    assert candidates[0].score == 0.75
    assert candidates[0].evidence == {
        "candidate_is_authoritative": False,
        "observed_label": "Customer revenue gross",
    }
    assert metrics == []


def _fact() -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="custom",
        concept="CustomerRevenueGross",
        label="Customer revenue gross",
        description="Revenue recognized from customer contracts",
        unit="USD",
        value_raw="100",
        value=Decimal("100"),
        start_date=date(2024, 9, 29),
        end_date=date(2025, 9, 27),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 10, 31),
        accession_number="0000000001-25-000001",
        frame=None,
        source="inline_xbrl_arelle",
        is_numeric=True,
    )
