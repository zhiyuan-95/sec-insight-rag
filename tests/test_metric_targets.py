from datetime import date
from decimal import Decimal
from pathlib import Path

from src.ingestion import company as company_module
from src.processing.metric_targets import (
    CanonicalMetricTarget,
    TargetConceptCandidate,
    all_canonical_metric_targets,
    missing_metric_targets,
)
from src.processing.xbrl_normalizer import NormalizedFact
from src.storage import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    ConceptMappingRecord,
    ConceptMappingRepository,
    connect_sqlite,
)


def test_canonical_metric_targets_keep_candidate_concepts() -> None:
    targets = all_canonical_metric_targets()
    revenue = next(target for target in targets if target.metric_name == "revenue")

    assert revenue.statement_type == "income_statement"
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in revenue.aliases
    assert any(
        candidate.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
        for candidate in revenue.candidate_concepts
    )


def test_approved_company_concept_profile_covers_missing_target(
    tmp_path: Path,
) -> None:
    cik = "0000001234"
    with connect_sqlite(tmp_path / "stock.db") as connection:
        repository = ConceptMappingRepository(connection)
        repository.initialize()
        repository.upsert_mappings(
            (
                ConceptMappingRecord(
                    taxonomy="custom",
                    concept="CustomerRevenueGross",
                    metric_name="revenue",
                    statement_type="income_statement",
                    scope_type=MAPPING_SCOPE_COMPANY,
                    scope_value=cik,
                    status=MAPPING_STATUS_APPROVED,
                    match_method="manual_review",
                    reviewed_by="tester",
                    evidence={"reason": "approved company concept profile test"},
                ),
            )
        )
        profile = company_module._load_approved_company_concept_profile(
            repository,
            cik,
            (),
        )

    target = CanonicalMetricTarget(
        metric_name="revenue",
        statement_type="income_statement",
        aliases=("RevenueFromContractWithCustomerExcludingAssessedTax",),
        candidate_concepts=(
            _target_candidate(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "revenue",
                "income_statement",
            ),
        ),
        industry_labels=("Common Base",),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )
    mapping_names = company_module._deterministic_mapping_names((), profile)

    assert profile.mapping_count == 1
    assert missing_metric_targets(
        (_fact("custom", "CustomerRevenueGross", "Customer revenue gross"),),
        (target,),
        mapping_names,
    ) == ()


def _target_candidate(
    concept: str,
    metric_name: str,
    statement_type: str,
) -> TargetConceptCandidate:
    return TargetConceptCandidate(
        taxonomy="us-gaap",
        concept=concept,
        metric_name=metric_name,
        statement_type=statement_type,
        industry_labels=("Common Base",),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )


def _fact(taxonomy: str, concept: str, label: str) -> NormalizedFact:
    return NormalizedFact(
        cik="0000001234",
        entity_name="Example Co.",
        taxonomy=taxonomy,
        concept=concept,
        label=label,
        description=f"{label} description",
        unit="USD",
        value_raw="100",
        value=Decimal("100"),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        period_type="duration",
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2026, 2, 1),
        accession_number="0000001234-26-000001",
        frame=None,
        source="companyfacts",
        is_numeric=True,
    )
