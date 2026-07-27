import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.processing.recovery_applications import (
    AffirmativeZeroEvidence,
    RECOVERY_APPLICATION_INVALID,
    RECOVERY_APPLICATION_SUCCEEDED,
    RecoveryApplication,
    RecoveryComponentApplication,
)
from src.processing.xbrl_normalizer import NormalizedFact
from src.processing.semantic_recommendations import (
    RECOMMENDATION_UNANIMOUS_FORMULA,
    RECOMMENDATION_UNANIMOUS_ZERO,
    SemanticJudgeIdentity,
    SemanticJudgeResponseRecord,
    SemanticRecommendationRecord,
    SemanticTargetComparison,
)
from src.storage import (
    CompanyRecord,
    CompanyRepository,
    FinancialMetric,
    FinancialMetricRepository,
    RecoveryApplicationRepository,
    RawFactRepository,
    SemanticRecommendationRepository,
    connect_sqlite,
)
from src.workflows.recovery_applications import persist_recovery_applications


def test_successful_application_persists_recovered_metric_and_failed_application_does_not(
    tmp_path: Path,
) -> None:
    recommendation = _recommendation_record()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_repository = CompanyRepository(connection)
        recommendation_repository = SemanticRecommendationRepository(connection)
        application_repository = RecoveryApplicationRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        raw_fact_repository = RawFactRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(
                cik="0000000001",
                name="Example Company",
                ticker="EXM",
            )
        )
        assert company.company_id is not None
        recommendation_repository.insert(recommendation)
        raw_fact_repository.upsert_facts(
            [
                _raw_fact("CashAndCashEquivalentsAtCarryingValue"),
                _duration_raw_fact(
                    concept="ProductRevenue",
                    value=Decimal("40"),
                    accession_number="0000000001-25-000002",
                    filing_date=date(2025, 2, 28),
                ),
                _duration_raw_fact(
                    concept="ServiceRevenue",
                    value=Decimal("60"),
                    accession_number="0000000001-25-000099",
                    filing_date=date(2025, 1, 31),
                ),
            ]
        )
        raw_facts = {
            record.fact.concept: record
            for record in raw_fact_repository.list_fact_records(
                "0000000001"
            )
        }
        direct_raw_fact = raw_facts[
            "CashAndCashEquivalentsAtCarryingValue"
        ]
        successful = _successful_application(
            product_raw_fact_id=raw_facts[
                "ProductRevenue"
            ].raw_fact_id,
            service_raw_fact_id=raw_facts[
                "ServiceRevenue"
            ].raw_fact_id,
        )
        failed = replace(
            successful,
            period_id="FY-2025",
            fiscal_year=2025,
            status=RECOVERY_APPLICATION_INVALID,
            failure_reason=(
                "component_fact_unavailable:custom:ProductRevenue"
            ),
            value_numeric=None,
            unit=None,
            period_type=None,
            start_date=None,
            end_date=None,
            filing_date=None,
            source_raw_fact_ids=(),
            source_accession_numbers=(),
            components=(),
        )
        metric_repository.upsert_metrics(
            [
                FinancialMetric(
                    company_id=company.company_id,
                    accession_number="0000000001-25-000001",
                    raw_fact_id=direct_raw_fact.raw_fact_id,
                    statement_type="balance_sheet",
                    metric_name="cash_and_cash_equivalents",
                    value_numeric=Decimal("25"),
                    value_raw="25",
                    unit="USD",
                    period_type="instant",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    end_date=date(2024, 12, 31),
                )
            ]
        )

        with pytest.raises(
            ValueError,
            match="source raw fact lineage is invalid",
        ):
            persist_recovery_applications(
                applications=(
                    replace(
                        successful,
                        period_id="FY-2025",
                        fiscal_year=2025,
                    ),
                ),
                metric_company_id=company.company_id,
                application_repository=application_repository,
                metric_repository=metric_repository,
            )

        stored = persist_recovery_applications(
            applications=(successful, failed),
            metric_company_id=company.company_id,
            application_repository=application_repository,
            metric_repository=metric_repository,
        )
        replayed = persist_recovery_applications(
            applications=(successful, failed),
            metric_company_id=company.company_id,
            application_repository=application_repository,
            metric_repository=metric_repository,
        )
        applications = application_repository.list_for_recommendation(
            recommendation.recommendation_request_id,
            recommendation.attempt_number,
        )
        metrics = metric_repository.list_metrics(
            company.company_id,
            active_only=False,
        )
        successful_store = next(
            item
            for item in stored
            if item.application.status
            == RECOVERY_APPLICATION_SUCCEEDED
        )
        with pytest.raises(
            ValueError,
            match="recovered metric does not match recovery application",
        ):
            metric_repository.upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        accession_number="0000000001-25-000002",
                        raw_fact_id=None,
                        origin="formula_recovery",
                        recovery_application_id=(
                            successful_store.recovery_application_id
                        ),
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("999"),
                        unit="USD",
                        period_type="duration",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        start_date=date(2024, 1, 1),
                        end_date=date(2024, 12, 31),
                        filing_date=date(2025, 2, 28),
                    )
                ]
            )

    assert replayed == stored
    assert applications == stored
    assert len(applications) == 2
    assert tuple(item.application.status for item in applications) == (
        RECOVERY_APPLICATION_SUCCEEDED,
        RECOVERY_APPLICATION_INVALID,
    )
    recovered = next(metric for metric in metrics if metric.metric_name == "revenue")
    direct = next(
        metric
        for metric in metrics
        if metric.metric_name == "cash_and_cash_equivalents"
    )
    successful_record = next(
        item
        for item in applications
        if item.application.status == RECOVERY_APPLICATION_SUCCEEDED
    )

    assert recovered.value_numeric == Decimal("100")
    assert recovered.origin == "formula_recovery"
    assert recovered.accession_number == "0000000001-25-000002"
    assert recovered.raw_fact_id is None
    assert (
        recovered.recovery_application_id
        == successful_record.recovery_application_id
    )
    assert (
        successful_record.application.recommendation_request_id
        == recommendation.recommendation_request_id
    )
    assert successful_record.application.recommendation_attempt_number == 1
    assert successful_record.application.source_raw_fact_ids == tuple(
        sorted(
            (
                raw_facts["ProductRevenue"].raw_fact_id,
                raw_facts["ServiceRevenue"].raw_fact_id,
            )
        )
    )
    assert direct.origin == "reported_mapping"
    assert direct.raw_fact_id == direct_raw_fact.raw_fact_id
    assert direct.recovery_application_id is None
    assert len(metrics) == 2


def test_application_decision_must_match_linked_unanimous_recommendation(
    tmp_path: Path,
) -> None:
    recommendation = _recommendation_record()
    mismatched = replace(
        _successful_application(),
        decision="zero",
        value_numeric=Decimal("0"),
        components=(),
        source_raw_fact_ids=(),
        source_accession_numbers=("0000000001-25-000001",),
    )

    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_repository = CompanyRepository(connection)
        recommendation_repository = SemanticRecommendationRepository(connection)
        application_repository = RecoveryApplicationRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        assert company.company_id is not None
        recommendation_repository.insert(recommendation)

        with pytest.raises(
            ValueError,
            match="does not match linked unanimous recommendation",
        ):
            persist_recovery_applications(
                applications=(mismatched,),
                metric_company_id=company.company_id,
                application_repository=application_repository,
                metric_repository=metric_repository,
            )

    assert application_repository.list_for_recommendation(
        recommendation.recommendation_request_id,
        recommendation.attempt_number,
    ) == ()


def test_successful_application_value_must_match_deterministic_formula(
    tmp_path: Path,
) -> None:
    recommendation = _recommendation_record()
    forged = replace(
        _successful_application(),
        value_numeric=Decimal("999"),
    )

    with connect_sqlite(tmp_path / "stock.db") as connection:
        CompanyRepository(connection).initialize()
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        assert company.company_id is not None
        SemanticRecommendationRepository(connection).insert(recommendation)
        application_repository = RecoveryApplicationRepository(connection)

        with pytest.raises(
            ValueError,
            match="deterministic recovery proof",
        ):
            persist_recovery_applications(
                applications=(forged,),
                metric_company_id=company.company_id,
                application_repository=application_repository,
                metric_repository=FinancialMetricRepository(connection),
            )

        assert application_repository.list_for_recommendation(
            recommendation.recommendation_request_id,
            recommendation.attempt_number,
        ) == ()


def test_application_company_must_match_metric_company(
    tmp_path: Path,
) -> None:
    recommendation = _recommendation_record()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_repository = CompanyRepository(connection)
        recommendation_repository = SemanticRecommendationRepository(connection)
        application_repository = RecoveryApplicationRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_repository.initialize()
        company_repository.upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        other = company_repository.upsert_company(
            CompanyRecord(cik="0000000002", name="Other Company")
        )
        assert other.company_id is not None
        recommendation_repository.insert(recommendation)

        with pytest.raises(
            ValueError,
            match="metric company does not match recovery application",
        ):
            persist_recovery_applications(
                applications=(_successful_application(),),
                metric_company_id=other.company_id,
                application_repository=application_repository,
                metric_repository=metric_repository,
            )

        assert application_repository.list_for_recommendation(
            recommendation.recommendation_request_id,
            recommendation.attempt_number,
        ) == ()


def test_reported_metric_requires_raw_fact_lineage(tmp_path: Path) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        CompanyRepository(connection).initialize()
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        assert company.company_id is not None

        with pytest.raises(
            ValueError,
            match="reported metric requires raw_fact_id",
        ):
            FinancialMetricRepository(connection).upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        accession_number="0000000001-25-000001",
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        unit="USD",
                        period_type="duration",
                    )
                ]
            )


def test_recovered_metric_requires_an_existing_application(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        CompanyRepository(connection).initialize()
        company = CompanyRepository(connection).upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        assert company.company_id is not None

        with pytest.raises(
            ValueError,
            match="existing recovery application",
        ):
            FinancialMetricRepository(connection).upsert_metrics(
                [
                    FinancialMetric(
                        company_id=company.company_id,
                        accession_number="0000000001-25-000001",
                        raw_fact_id=None,
                        origin="formula_recovery",
                        recovery_application_id=999,
                        statement_type="income_statement",
                        metric_name="revenue",
                        value_numeric=Decimal("100"),
                        unit="USD",
                        period_type="duration",
                    )
                ]
            )


def test_affirmative_zero_application_persists_with_distinct_origin(
    tmp_path: Path,
) -> None:
    recommendation = _zero_recommendation_record()

    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_repository = CompanyRepository(connection)
        recommendation_repository = SemanticRecommendationRepository(connection)
        application_repository = RecoveryApplicationRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_repository.initialize()
        company = company_repository.upsert_company(
            CompanyRecord(cik="0000000001", name="Example Company")
        )
        assert company.company_id is not None
        recommendation_repository.insert(recommendation)
        raw_fact_repository = RawFactRepository(connection)
        raw_fact_repository.upsert_facts(
            [
                _duration_raw_fact(
                    concept="ServiceRevenue",
                    value=Decimal("0"),
                    accession_number="0000000001-25-000001",
                    filing_date=date(2025, 1, 31),
                )
            ]
        )
        zero_raw_fact = raw_fact_repository.list_fact_records(
            "0000000001"
        )[0]
        application = _successful_zero_application(
            raw_fact_id=zero_raw_fact.raw_fact_id
        )

        stored = persist_recovery_applications(
            applications=(application,),
            metric_company_id=company.company_id,
            application_repository=application_repository,
            metric_repository=metric_repository,
        )
        metrics = metric_repository.list_metrics(company.company_id)

    assert len(stored) == 1
    assert len(metrics) == 1
    assert metrics[0].value_numeric == Decimal("0")
    assert metrics[0].origin == "affirmative_zero_recovery"
    assert (
        metrics[0].recovery_application_id
        == stored[0].recovery_application_id
    )


def _successful_application(
    *,
    product_raw_fact_id: int = 102,
    service_raw_fact_id: int = 101,
) -> RecoveryApplication:
    components = (
        RecoveryComponentApplication(
            taxonomy="custom",
            concept="ProductRevenue",
            operator="+",
            evidence_refs=("concept-productrevenue",),
            raw_fact_id=product_raw_fact_id,
            accession_number="0000000001-25-000002",
            source_system="inline_xbrl",
            value_numeric=Decimal("40"),
            unit="USD",
            period_type="duration",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            filing_date=date(2025, 2, 28),
        ),
        RecoveryComponentApplication(
            taxonomy="custom",
            concept="ServiceRevenue",
            operator="+",
            evidence_refs=("concept-servicerevenue",),
            raw_fact_id=service_raw_fact_id,
            accession_number="0000000001-25-000099",
            source_system="inline_xbrl",
            value_numeric=Decimal("60"),
            unit="USD",
            period_type="duration",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            filing_date=date(2025, 1, 31),
        ),
    )
    return RecoveryApplication(
        recommendation_request_id="semantic-recommendation:test",
        recommendation_attempt_number=1,
        company_id="0000000001",
        period_id="FY-2024",
        target_metric_name="revenue",
        statement_type="income_statement",
        decision="formula",
        status=RECOVERY_APPLICATION_SUCCEEDED,
        failure_reason=None,
        fiscal_year=2024,
        fiscal_period="FY",
        value_numeric=Decimal("100"),
        unit="USD",
        period_type="duration",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        filing_date=date(2025, 2, 28),
        source_raw_fact_ids=tuple(
            sorted((product_raw_fact_id, service_raw_fact_id))
        ),
        source_accession_numbers=(
            "0000000001-25-000002",
            "0000000001-25-000099",
        ),
        components=components,
    )


def _successful_zero_application(
    *,
    raw_fact_id: int = 101,
) -> RecoveryApplication:
    evidence = AffirmativeZeroEvidence(
        company_id="0000000001",
        target_metric_name="revenue",
        statement_type="income_statement",
        evidence_id="concept-servicerevenue",
        taxonomy="custom",
        concept="ServiceRevenue",
        raw_fact_id=raw_fact_id,
        arelle_fact_id=f"fact-{raw_fact_id}",
        value_numeric=Decimal("0"),
        source_accession_number="0000000001-25-000001",
        source_system="inline_xbrl",
        fiscal_year=2024,
        fiscal_period="FY",
        unit="USD",
        period_type="duration",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        filing_date=date(2025, 1, 31),
        dimensions=(),
        is_consolidated=True,
    )
    return RecoveryApplication(
        recommendation_request_id="semantic-recommendation:zero-test",
        recommendation_attempt_number=1,
        company_id="0000000001",
        period_id="FY-2024",
        target_metric_name="revenue",
        statement_type="income_statement",
        decision="zero",
        status=RECOVERY_APPLICATION_SUCCEEDED,
        failure_reason=None,
        fiscal_year=2024,
        fiscal_period="FY",
        value_numeric=Decimal("0"),
        unit="USD",
        period_type="duration",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        filing_date=date(2025, 1, 31),
        source_raw_fact_ids=(raw_fact_id,),
        source_accession_numbers=("0000000001-25-000001",),
        components=(),
        zero_evidence=evidence,
    )


def _raw_fact(concept: str) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        description=None,
        unit="USD",
        value_raw="25",
        value=Decimal("25"),
        start_date=None,
        end_date=date(2024, 12, 31),
        period_type="instant",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 1, 31),
        accession_number="0000000001-25-000001",
        frame=None,
        source="inline_xbrl",
        is_numeric=True,
        is_consolidated=True,
    )


def _duration_raw_fact(
    *,
    concept: str,
    value: Decimal,
    accession_number: str,
    filing_date: date,
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="custom",
        concept=concept,
        label=concept,
        description=f"{concept} documentation",
        unit="USD",
        value_raw=str(value),
        value=value,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=filing_date,
        accession_number=accession_number,
        frame=None,
        source="inline_xbrl",
        is_numeric=True,
        is_consolidated=True,
    )


def _recommendation_record() -> SemanticRecommendationRecord:
    canonical = json.dumps(
        {
            "components": [
                {
                    "concept": "ProductRevenue",
                    "evidence_refs": ["concept-productrevenue"],
                    "operator": "+",
                    "taxonomy": "custom",
                },
                {
                    "concept": "ServiceRevenue",
                    "evidence_refs": ["concept-servicerevenue"],
                    "operator": "+",
                    "taxonomy": "custom",
                },
            ],
            "decision": "formula",
            "evidence_refs": [
                "concept-productrevenue",
                "concept-servicerevenue",
            ],
            "statement_type": "income_statement",
            "target_metric_name": "revenue",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    judge = SemanticJudgeIdentity("test", "test-model")
    response = SemanticJudgeResponseRecord(
        judge=judge,
        response_status="completed",
        started_at="2026-07-27T12:00:00+00:00",
        completed_at="2026-07-27T12:00:01+00:00",
        response_json="{}",
        canonical_response_json=canonical,
        error="",
    )
    return SemanticRecommendationRecord(
        recommendation_request_id="semantic-recommendation:test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024", "FY-2025"),
        packet_content_sha256="packet-hash",
        packet_json='{"schema_version":"1"}',
        prompt_version="semantic_recommendation_v1",
        judge_lineup=(judge, judge, judge),
        judge_responses=(response, response, response),
        target_comparisons=(
            SemanticTargetComparison(
                target_metric_name="revenue",
                statement_type="income_statement",
                outcome=RECOMMENDATION_UNANIMOUS_FORMULA,
                judge_canonical_json=(canonical, canonical, canonical),
                unanimous_canonical_json=canonical,
            ),
        ),
        outcome=RECOMMENDATION_UNANIMOUS_FORMULA,
        created_at="2026-07-27T12:00:02+00:00",
    )


def _zero_recommendation_record() -> SemanticRecommendationRecord:
    canonical = (
        '{"components":[],"decision":"zero",'
        '"evidence_refs":["concept-servicerevenue"],'
        '"statement_type":"income_statement",'
        '"target_metric_name":"revenue"}'
    )
    judge = SemanticJudgeIdentity("test", "test-model")
    response = SemanticJudgeResponseRecord(
        judge=judge,
        response_status="completed",
        started_at="2026-07-27T12:00:00+00:00",
        completed_at="2026-07-27T12:00:01+00:00",
        response_json="{}",
        canonical_response_json=canonical,
        error="",
    )
    return SemanticRecommendationRecord(
        recommendation_request_id="semantic-recommendation:zero-test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024",),
        packet_content_sha256="zero-packet-hash",
        packet_json=json.dumps(
            {
                "arelle_evidence_status": "available",
                "concepts": [
                    {
                        "component_eligible": True,
                        "concept": "ServiceRevenue",
                        "evidence_id": "concept-servicerevenue",
                        "taxonomy": "custom",
                    }
                ],
                "schema_version": "1",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        prompt_version="semantic_recommendation_v1",
        judge_lineup=(judge, judge, judge),
        judge_responses=(response, response, response),
        target_comparisons=(
            SemanticTargetComparison(
                target_metric_name="revenue",
                statement_type="income_statement",
                outcome=RECOMMENDATION_UNANIMOUS_ZERO,
                judge_canonical_json=(canonical, canonical, canonical),
                unanimous_canonical_json=canonical,
            ),
        ),
        outcome=RECOMMENDATION_UNANIMOUS_ZERO,
        created_at="2026-07-27T12:00:02+00:00",
    )
