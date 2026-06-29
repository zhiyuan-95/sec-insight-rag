import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.ingestion import company as company_module
from src.processing.semantic_mapping import (
    CanonicalMetricTarget,
    TargetConceptCandidate,
    all_canonical_metric_targets,
    generate_semantic_mapping_candidates,
    missing_metric_targets,
    prewarm_all_target_candidate_embeddings,
)
from src.processing.xbrl_normalizer import NormalizedFact
from src.storage import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_STATUS_APPROVED,
    ConceptMappingRecord,
    ConceptMappingRepository,
    connect_sqlite,
)


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def get_text_embedding_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(tuple(texts))
        return [_vector_for_text(text) for text in texts]


def test_semantic_mapping_embeds_each_target_xbrl_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    embedding_model = FakeEmbeddingModel()
    monkeypatch.setattr(
        "src.processing.semantic_mapping._embedding_model",
        lambda model_name, cache_dir: embedding_model,
    )
    target = CanonicalMetricTarget(
        metric_name="revenue",
        statement_type="income_statement",
        aliases=(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ),
        candidate_concepts=(
            _target_candidate(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "revenue",
                "income_statement",
            ),
            _target_candidate("SalesRevenueNet", "revenue", "income_statement"),
        ),
        industry_labels=("Common Base",),
        required_for_core=True,
        required_for_specialized_indicators=False,
    )

    candidates = generate_semantic_mapping_candidates(
        (
            _fact("custom", "CustomerRevenueGross", "Customer revenue gross"),
            _fact("custom", "RetailSalesRevenue", "Retail sales revenue"),
        ),
        (target,),
        set(),
        embedding_model_name="fake-model",
        model_cache_dir=tmp_path / "model-cache",
        target_embedding_path=tmp_path / "target-embeddings.json",
        minimum_similarity=0.99,
        candidates_per_target=1,
    )

    assert len(candidates) == 2
    assert {
        candidate.evidence["target_candidate_xbrl_concept"]
        for candidate in candidates
    } == {
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    }
    assert all(
        candidate.evidence["embedding_granularity"]
        == "target_xbrl_concept_candidate"
        for candidate in candidates
    )
    assert len(embedding_model.calls[0]) == 2
    assert all(
        "Candidate SEC XBRL concept:" in text
        for text in embedding_model.calls[0]
    )
    cache = json.loads((tmp_path / "target-embeddings.json").read_text(encoding="utf-8"))
    assert cache["embedding_granularity"] == "target_xbrl_concept_candidate"
    assert any(
        key.endswith(":us-gaap:SalesRevenueNet")
        for key in cache["vectors_by_target_candidate"]
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


def test_prewarm_all_target_candidate_embeddings_caches_catalog_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    embedding_model = FakeEmbeddingModel()
    monkeypatch.setattr(
        "src.processing.semantic_mapping._embedding_model",
        lambda model_name, cache_dir: embedding_model,
    )
    target_embedding_path = tmp_path / "target-embeddings.json"

    result = prewarm_all_target_candidate_embeddings(
        embedding_model_name="fake-model",
        model_cache_dir=tmp_path / "model-cache",
        target_embedding_path=target_embedding_path,
    )
    expected_candidate_count = sum(
        len(target.candidate_concepts)
        for target in all_canonical_metric_targets()
    )

    assert result.target_candidate_count == expected_candidate_count
    assert result.cached_vector_count == expected_candidate_count
    assert result.created_vector_count == expected_candidate_count
    assert result.reused_vector_count == 0
    assert len(embedding_model.calls) == 1
    cache = json.loads(target_embedding_path.read_text(encoding="utf-8"))
    assert len(cache["vectors_by_target_candidate"]) == expected_candidate_count
    assert "debt_current:balance_sheet:us-gaap:DebtCurrent" in cache["vectors_by_target_candidate"]

    second_result = prewarm_all_target_candidate_embeddings(
        embedding_model_name="fake-model",
        model_cache_dir=tmp_path / "model-cache",
        target_embedding_path=target_embedding_path,
    )

    assert second_result.created_vector_count == 0
    assert second_result.reused_vector_count == expected_candidate_count
    assert len(embedding_model.calls) == 1


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


def _vector_for_text(text: str) -> list[float]:
    if (
        "RevenueFromContractWithCustomerExcludingAssessedTax" in text
        or "customer revenue gross" in text.lower()
    ):
        return [1.0, 0.0]
    if "SalesRevenueNet" in text or "retail sales revenue" in text.lower():
        return [0.0, 1.0]
    return [0.5, 0.5]
