import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.processing import NormalizedFact
from src.processing.recovery_applications import (
    RECOVERY_APPLICATION_SUCCEEDED,
    RecoveryApplication,
    RecoveryComponentApplication,
)
from src.processing.semantic_recommendations import (
    RECOMMENDATION_UNANIMOUS_FORMULA,
    SemanticJudgeIdentity,
    SemanticJudgeResponseRecord,
    SemanticRecommendationRecord,
    SemanticTargetComparison,
)
from src.storage import (
    CompanyMetricSnapshotRepository,
    CompanyRecord,
    CompanyRepository,
    FinancialMetric,
    FinancialMetricRepository,
    PublishedCompanyMetricSnapshot,
    RawFactRepository,
    RecoveryApplicationRepository,
    SemanticRecommendationRepository,
    SnapshotComponentVersion,
    SnapshotTargetStatus,
    StoredRawFact,
    connect_sqlite,
)
from src.workflows import (
    StagedCompanyMetricSnapshot,
    persist_recovery_applications,
    publish_company_metric_snapshot,
)


def test_company_snapshot_publication_exposes_one_versioned_current_state(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        snapshot_repository = CompanyMetricSnapshotRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_id, raw_fact, metric = _seed_revenue_metric(connection)
        stage = StagedCompanyMetricSnapshot(
            company_id=company_id,
            raw_fact_ids=(raw_fact.raw_fact_id,),
            metrics=(metric,),
            target_statuses=(
                SnapshotTargetStatus(
                    statement_type="income_statement",
                    metric_name="revenue",
                    period_type="duration",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    status="mapped",
                ),
            ),
            component_versions=(
                SnapshotComponentVersion(
                    component="mapping_policy",
                    version="1",
                ),
            ),
            completed_at=datetime(
                2026,
                7,
                27,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        published = publish_company_metric_snapshot(
            stage=stage,
            connection=connection,
        )

        assert published.snapshot_version == 1
        assert published.status == "published"
        assert snapshot_repository.get_current(company_id) == published
        assert snapshot_repository.list_history(company_id) == (
            published,
        )
        assert metric_repository.list_metrics(
            company_id,
            active_only=False,
        ) == [published.metrics[0]]
        assert published.raw_fact_ids == (raw_fact.raw_fact_id,)
        assert published.component_versions == stage.component_versions


def test_company_snapshot_rejects_direct_metric_without_staged_raw_evidence(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        snapshot_repository = CompanyMetricSnapshotRepository(connection)
        metric_repository = FinancialMetricRepository(connection)
        company_id, _, metric = _seed_revenue_metric(connection)
        stage = StagedCompanyMetricSnapshot(
            company_id=company_id,
            raw_fact_ids=(),
            metrics=(metric,),
            target_statuses=(
                SnapshotTargetStatus(
                    statement_type="income_statement",
                    metric_name="revenue",
                    period_type="duration",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    status="mapped",
                ),
            ),
            component_versions=(
                SnapshotComponentVersion(
                    component="mapping_policy",
                    version="1",
                ),
            ),
            completed_at=datetime(
                2026,
                7,
                27,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        )

        with pytest.raises(
            ValueError,
            match="direct metric raw fact is not staged",
        ):
            publish_company_metric_snapshot(
                stage=stage,
                connection=connection,
            )

        assert snapshot_repository.get_current(company_id) is None
        assert metric_repository.list_metrics(
            company_id,
            active_only=False,
        ) == []


def test_company_snapshot_refuses_to_silently_remove_stale_metric(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)
        snapshot_repository = CompanyMetricSnapshotRepository(connection)
        metric_repository = FinancialMetricRepository(connection)

        with pytest.raises(
            ValueError,
            match="stale metric requires target failure status",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=first.raw_fact_ids,
                    metrics=(),
                    target_statuses=(),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="2",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        28,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert snapshot_repository.get_current(company_id) == first
        assert snapshot_repository.list_history(company_id) == (first,)
        assert metric_repository.list_metrics(
            company_id,
            active_only=False,
        ) == [first.metrics[0]]


def test_failed_target_is_visible_while_unrelated_metric_is_published(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)
        raw_fact_repository = RawFactRepository(connection)
        raw_fact_repository.upsert_facts([_cash_fact()])
        raw_facts = raw_fact_repository.list_fact_records("0000000001")
        raw_fact_by_concept = {
            record.fact.concept: record
            for record in raw_facts
        }
        cash_raw_fact = raw_fact_by_concept[
            "CashAndCashEquivalentsAtCarryingValue"
        ]
        cash_metric = FinancialMetric(
            company_id=company_id,
            accession_number="0000000001-25-000001",
            raw_fact_id=cash_raw_fact.raw_fact_id,
            statement_type="balance_sheet",
            metric_name="cash_and_cash_equivalents",
            value_numeric=Decimal("25"),
            value_raw="25",
            unit="USD",
            period_type="instant",
            fiscal_year=2024,
            fiscal_period="FY",
            end_date=date(2024, 12, 31),
            filing_date=date(2025, 2, 1),
        )

        second = publish_company_metric_snapshot(
            stage=StagedCompanyMetricSnapshot(
                company_id=company_id,
                raw_fact_ids=tuple(
                    sorted(record.raw_fact_id for record in raw_facts)
                ),
                metrics=(cash_metric,),
                target_statuses=(
                    SnapshotTargetStatus(
                        statement_type="balance_sheet",
                        metric_name="cash_and_cash_equivalents",
                        period_type="instant",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        status="mapped",
                    ),
                    SnapshotTargetStatus(
                        statement_type="income_statement",
                        metric_name="revenue",
                        period_type="duration",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        status="invalid_proposal",
                        failure_reason="component_fact_unavailable",
                    ),
                ),
                component_versions=(
                    SnapshotComponentVersion(
                        component="mapping_policy",
                        version="2",
                    ),
                ),
                completed_at=datetime(
                    2026,
                    7,
                    28,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            connection=connection,
        )

        current = CompanyMetricSnapshotRepository(connection).get_current(
            company_id
        )
        history = CompanyMetricSnapshotRepository(connection).list_history(
            company_id
        )
        current_metrics = FinancialMetricRepository(connection).list_metrics(
            company_id,
            active_only=False,
        )

        assert current == second
        assert second.snapshot_version == 2
        assert tuple(metric.metric_name for metric in second.metrics) == (
            "cash_and_cash_equivalents",
        )
        assert second.target_statuses[1].failure_reason == (
            "component_fact_unavailable"
        )
        assert tuple(metric.metric_name for metric in current_metrics) == (
            "cash_and_cash_equivalents",
        )
        assert history == (first, second)
        assert history[0].metrics[0].metric_name == "revenue"


def test_publication_failure_rolls_back_metrics_and_current_snapshot(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)
        invalid_metric = replace(first.metrics[0], raw_fact_id=None)

        with pytest.raises(
            ValueError,
            match="reported metric requires raw_fact_id",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=first.raw_fact_ids,
                    metrics=(invalid_metric,),
                    target_statuses=first.target_statuses,
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="2",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        28,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        snapshot_repository = CompanyMetricSnapshotRepository(connection)
        assert snapshot_repository.get_current(company_id) == first
        assert snapshot_repository.list_history(company_id) == (first,)
        assert FinancialMetricRepository(connection).list_metrics(
            company_id,
            active_only=False,
        ) == [first.metrics[0]]


def test_company_snapshot_requires_explicit_component_versions(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)

        with pytest.raises(
            ValueError,
            match="snapshot requires component versions",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=first.raw_fact_ids,
                    metrics=first.metrics,
                    target_statuses=first.target_statuses,
                    component_versions=(),
                    completed_at=datetime(
                        2026,
                        7,
                        28,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert (
            CompanyMetricSnapshotRepository(connection).get_current(company_id)
            == first
        )


def test_company_snapshot_rejects_recovery_with_unstaged_source_fact(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_facts, recovered = _seed_recovered_revenue(connection)
        metric_repository = FinancialMetricRepository(connection)

        with pytest.raises(
            ValueError,
            match="recovered metric source facts are not staged",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(
                        raw_facts["ProductRevenue"].raw_fact_id,
                    ),
                    metrics=(recovered,),
                    target_statuses=(
                        SnapshotTargetStatus(
                            statement_type="income_statement",
                            metric_name="revenue",
                            period_type="duration",
                            fiscal_year=2024,
                            fiscal_period="FY",
                            status="recovered",
                        ),
                    ),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert (
            CompanyMetricSnapshotRepository(connection).get_current(
                company_id
            )
            is None
        )
        assert metric_repository.list_metrics(
            company_id,
            active_only=False,
        ) == [recovered]


def test_company_snapshot_publishes_direct_and_recovered_metrics_together(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_facts, recovered = _seed_recovered_revenue(connection)
        product_raw_fact = raw_facts["ProductRevenue"]
        direct = FinancialMetric(
            company_id=company_id,
            accession_number=product_raw_fact.fact.accession_number or "",
            raw_fact_id=product_raw_fact.raw_fact_id,
            statement_type="income_statement",
            metric_name="product_revenue",
            value_numeric=product_raw_fact.fact.value,
            value_raw=product_raw_fact.fact.value_raw,
            unit=product_raw_fact.fact.unit,
            period_type=product_raw_fact.fact.period_type,
            fiscal_year=product_raw_fact.fact.fiscal_year,
            fiscal_period=product_raw_fact.fact.fiscal_period,
            start_date=product_raw_fact.fact.start_date,
            end_date=product_raw_fact.fact.end_date,
            filing_date=product_raw_fact.fact.filed_date,
        )

        published = publish_company_metric_snapshot(
            stage=StagedCompanyMetricSnapshot(
                company_id=company_id,
                raw_fact_ids=tuple(
                    sorted(
                        record.raw_fact_id
                        for record in raw_facts.values()
                    )
                ),
                metrics=(direct, recovered),
                target_statuses=(
                    SnapshotTargetStatus(
                        statement_type="income_statement",
                        metric_name="product_revenue",
                        period_type="duration",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        status="mapped",
                    ),
                    SnapshotTargetStatus(
                        statement_type="income_statement",
                        metric_name="revenue",
                        period_type="duration",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        status="recovered",
                    ),
                ),
                component_versions=(
                    SnapshotComponentVersion(
                        component="mapping_policy",
                        version="1",
                    ),
                    SnapshotComponentVersion(
                        component="semantic_judges",
                        version="gpt-5-mini+gemini-3.1-flash-lite+gemini-2.5-flash",
                    ),
                ),
                completed_at=datetime(
                    2026,
                    7,
                    27,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            connection=connection,
        )

        assert tuple(metric.metric_name for metric in published.metrics) == (
            "product_revenue",
            "revenue",
        )
        assert tuple(metric.origin for metric in published.metrics) == (
            "reported_mapping",
            "formula_recovery",
        )
        assert published.metrics[1].recovery_application_id is not None
        assert (
            CompanyMetricSnapshotRepository(connection).get_current(company_id)
            == published
        )


def test_company_snapshot_refuses_an_existing_caller_transaction(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        CompanyRepository(connection).initialize()
        connection.execute("BEGIN")

        with pytest.raises(
            ValueError,
            match="snapshot publication requires transaction ownership",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=999,
                    raw_fact_ids=(),
                    metrics=(),
                    target_statuses=(),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert connection.in_transaction is True
        connection.rollback()


def test_company_snapshot_requires_status_for_every_current_metric(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)

        with pytest.raises(
            ValueError,
            match="current metric requires target status",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=first.raw_fact_ids,
                    metrics=first.metrics,
                    target_statuses=(),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="2",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        28,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert (
            CompanyMetricSnapshotRepository(connection).get_current(company_id)
            == first
        )


def test_first_snapshot_archives_preexisting_metric_that_becomes_stale(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_facts, recovered = _seed_recovered_revenue(connection)
        snapshot_repository = CompanyMetricSnapshotRepository(connection)

        published = publish_company_metric_snapshot(
            stage=StagedCompanyMetricSnapshot(
                company_id=company_id,
                raw_fact_ids=tuple(
                    sorted(
                        record.raw_fact_id
                        for record in raw_facts.values()
                    )
                ),
                metrics=(),
                target_statuses=(
                    SnapshotTargetStatus(
                        statement_type="income_statement",
                        metric_name="revenue",
                        period_type="duration",
                        fiscal_year=2024,
                        fiscal_period="FY",
                        status="invalid_proposal",
                        failure_reason="component_fact_unavailable",
                    ),
                ),
                component_versions=(
                    SnapshotComponentVersion(
                        component="mapping_policy",
                        version="1",
                    ),
                ),
                completed_at=datetime(
                    2026,
                    7,
                    27,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            connection=connection,
        )

        audit = snapshot_repository.list_metric_audit(company_id)
        assert FinancialMetricRepository(connection).list_metrics(
            company_id,
            active_only=False,
        ) == []
        assert published.metrics == ()
        assert len(audit) == 1
        assert audit[0].metric == recovered
        assert (
            audit[0].invalidated_by_company_metric_snapshot_id
            == published.company_metric_snapshot_id
        )
        assert audit[0].reason == "component_fact_unavailable"


@pytest.mark.parametrize(
    ("duplicate_kind", "error_match"),
    [
        ("target_status", "duplicate snapshot target status"),
        ("component_version", "duplicate snapshot component version"),
    ],
)
def test_company_snapshot_rejects_ambiguous_status_or_version_metadata(
    tmp_path: Path,
    duplicate_kind: str,
    error_match: str,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, first = _publish_revenue_snapshot(connection)
        target_statuses = first.target_statuses
        component_versions = first.component_versions
        if duplicate_kind == "target_status":
            target_statuses = target_statuses + target_statuses
        else:
            component_versions = component_versions + component_versions

        with pytest.raises(ValueError, match=error_match):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=first.raw_fact_ids,
                    metrics=first.metrics,
                    target_statuses=target_statuses,
                    component_versions=component_versions,
                    completed_at=datetime(
                        2026,
                        7,
                        28,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert (
            CompanyMetricSnapshotRepository(connection).get_current(company_id)
            == first
        )


def test_company_snapshot_rejects_failed_status_for_current_metric(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_fact, metric = _seed_revenue_metric(connection)

        with pytest.raises(
            ValueError,
            match="current metric requires successful target status",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(raw_fact.raw_fact_id,),
                    metrics=(metric,),
                    target_statuses=(
                        SnapshotTargetStatus(
                            statement_type="income_statement",
                            metric_name="revenue",
                            period_type="duration",
                            fiscal_year=2024,
                            fiscal_period="FY",
                            status="invalid_proposal",
                            failure_reason="component_fact_unavailable",
                        ),
                    ),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )

        assert CompanyMetricSnapshotRepository(connection).get_current(
            company_id
        ) is None


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [
        ("accession_number", "0000000001-25-999999"),
        ("value_numeric", Decimal("999")),
        ("unit", "shares"),
        ("period_type", "instant"),
        ("fiscal_year", 2023),
        ("fiscal_period", "Q4"),
        ("start_date", date(2024, 2, 1)),
        ("end_date", date(2024, 11, 30)),
        ("filing_date", date(2025, 3, 1)),
    ],
)
def test_company_snapshot_rejects_direct_metric_that_mismatches_raw_fact(
    tmp_path: Path,
    changed_field: str,
    changed_value: object,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_fact, metric = _seed_revenue_metric(connection)
        mismatched = replace(metric, **{changed_field: changed_value})

        with pytest.raises(
            ValueError,
            match="direct metric does not match staged raw fact",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(raw_fact.raw_fact_id,),
                    metrics=(mismatched,),
                    target_statuses=(
                        SnapshotTargetStatus(
                            statement_type="income_statement",
                            metric_name="revenue",
                            period_type=mismatched.period_type,
                            fiscal_year=mismatched.fiscal_year,
                            fiscal_period=mismatched.fiscal_period,
                            status="mapped",
                        ),
                    ),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )


def test_company_snapshot_rejects_duplicate_current_target_metrics(
    tmp_path: Path,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_fact, metric = _seed_revenue_metric(connection)

        with pytest.raises(
            ValueError,
            match="duplicate snapshot current metric target",
        ):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(raw_fact.raw_fact_id,),
                    metrics=(metric, metric),
                    target_statuses=(
                        SnapshotTargetStatus(
                            statement_type="income_statement",
                            metric_name="revenue",
                            period_type="duration",
                            fiscal_year=2024,
                            fiscal_period="FY",
                            status="mapped",
                        ),
                    ),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )


@pytest.mark.parametrize(
    ("target_statuses", "component_versions", "error_match"),
    [
        (
            (
                SnapshotTargetStatus(
                    statement_type="income_statement",
                    metric_name="revenue",
                    period_type="duration",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    status=" ",
                ),
            ),
            (
                SnapshotComponentVersion(
                    component="mapping_policy",
                    version="1",
                ),
            ),
            "snapshot target status requires nonblank identity and status",
        ),
        (
            (
                SnapshotTargetStatus(
                    statement_type="income_statement",
                    metric_name="revenue",
                    period_type="duration",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    status="mapped",
                ),
            ),
            (
                SnapshotComponentVersion(
                    component="mapping_policy",
                    version=" ",
                ),
            ),
            "snapshot component version requires nonblank values",
        ),
    ],
)
def test_company_snapshot_rejects_blank_publication_metadata(
    tmp_path: Path,
    target_statuses: tuple[SnapshotTargetStatus, ...],
    component_versions: tuple[SnapshotComponentVersion, ...],
    error_match: str,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_fact, metric = _seed_revenue_metric(connection)

        with pytest.raises(ValueError, match=error_match):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(raw_fact.raw_fact_id,),
                    metrics=(metric,),
                    target_statuses=target_statuses,
                    component_versions=component_versions,
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )


@pytest.mark.parametrize(
    ("status", "failure_reason", "error_match"),
    [
        (
            "mapped",
            None,
            "successful target status requires current metric",
        ),
        (
            "invalid_proposal",
            None,
            "failed target status requires failure reason",
        ),
        (
            "invalid_proposal",
            " ",
            "failed target status requires failure reason",
        ),
    ],
)
def test_company_snapshot_rejects_status_without_consistent_outcome(
    tmp_path: Path,
    status: str,
    failure_reason: str | None,
    error_match: str,
) -> None:
    with connect_sqlite(tmp_path / "stock.db") as connection:
        company_id, raw_fact, _ = _seed_revenue_metric(connection)

        with pytest.raises(ValueError, match=error_match):
            publish_company_metric_snapshot(
                stage=StagedCompanyMetricSnapshot(
                    company_id=company_id,
                    raw_fact_ids=(raw_fact.raw_fact_id,),
                    metrics=(),
                    target_statuses=(
                        SnapshotTargetStatus(
                            statement_type="income_statement",
                            metric_name="revenue",
                            period_type="duration",
                            fiscal_year=2024,
                            fiscal_period="FY",
                            status=status,
                            failure_reason=failure_reason,
                        ),
                    ),
                    component_versions=(
                        SnapshotComponentVersion(
                            component="mapping_policy",
                            version="1",
                        ),
                    ),
                    completed_at=datetime(
                        2026,
                        7,
                        27,
                        12,
                        0,
                        tzinfo=timezone.utc,
                    ),
                ),
                connection=connection,
            )


def _revenue_fact() -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        label="Revenue",
        description="Revenue from customers",
        unit="USD",
        value_raw="100",
        value=Decimal("100"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 2, 1),
        accession_number="0000000001-25-000001",
        frame=None,
        source="inline_xbrl",
        quality_flags=(),
        is_numeric=True,
    )


def _cash_fact() -> NormalizedFact:
    return NormalizedFact(
        cik="0000000001",
        entity_name="Example Company",
        taxonomy="us-gaap",
        concept="CashAndCashEquivalentsAtCarryingValue",
        label="Cash and cash equivalents",
        description="Cash and cash equivalents",
        unit="USD",
        value_raw="25",
        value=Decimal("25"),
        start_date=None,
        end_date=date(2024, 12, 31),
        period_type="instant",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 2, 1),
        accession_number="0000000001-25-000001",
        frame=None,
        source="inline_xbrl",
        quality_flags=(),
        is_numeric=True,
    )


def _recovery_component_fact(
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
        description=concept,
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
        quality_flags=(),
        is_numeric=True,
    )


def _formula_application(
    *,
    product_raw_fact_id: int,
    service_raw_fact_id: int,
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
        recommendation_request_id="semantic-recommendation:snapshot-test",
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


def _formula_recommendation() -> SemanticRecommendationRecord:
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
        recommendation_request_id="semantic-recommendation:snapshot-test",
        attempt_number=1,
        company_id="0000000001",
        period_ids=("FY-2024",),
        packet_content_sha256="snapshot-packet-hash",
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


def _seed_recovered_revenue(
    connection: sqlite3.Connection,
) -> tuple[int, dict[str, StoredRawFact], FinancialMetric]:
    company_repository = CompanyRepository(connection)
    raw_fact_repository = RawFactRepository(connection)
    recommendation_repository = SemanticRecommendationRepository(connection)
    application_repository = RecoveryApplicationRepository(connection)
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
    raw_fact_repository.upsert_facts(
        [
            _recovery_component_fact(
                concept="ProductRevenue",
                value=Decimal("40"),
                accession_number="0000000001-25-000002",
                filing_date=date(2025, 2, 28),
            ),
            _recovery_component_fact(
                concept="ServiceRevenue",
                value=Decimal("60"),
                accession_number="0000000001-25-000099",
                filing_date=date(2025, 1, 31),
            ),
        ]
    )
    raw_facts = {
        record.fact.concept: record
        for record in raw_fact_repository.list_fact_records(company.cik)
    }
    recommendation_repository.insert(_formula_recommendation())
    persist_recovery_applications(
        applications=(
            _formula_application(
                product_raw_fact_id=raw_facts[
                    "ProductRevenue"
                ].raw_fact_id,
                service_raw_fact_id=raw_facts[
                    "ServiceRevenue"
                ].raw_fact_id,
            ),
        ),
        metric_company_id=company.company_id,
        application_repository=application_repository,
        metric_repository=metric_repository,
    )
    recovered = metric_repository.list_metrics(
        company.company_id,
        active_only=False,
    )[0]
    return company.company_id, raw_facts, recovered


def _seed_revenue_metric(
    connection: sqlite3.Connection,
) -> tuple[int, StoredRawFact, FinancialMetric]:
    company_repository = CompanyRepository(connection)
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
    raw_fact_repository.upsert_facts([_revenue_fact()])
    raw_fact = raw_fact_repository.list_fact_records(company.cik)[0]
    return (
        company.company_id,
        raw_fact,
        FinancialMetric(
            company_id=company.company_id,
            accession_number="0000000001-25-000001",
            raw_fact_id=raw_fact.raw_fact_id,
            statement_type="income_statement",
            metric_name="revenue",
            value_numeric=Decimal("100"),
            value_raw="100",
            unit="USD",
            period_type="duration",
            fiscal_year=2024,
            fiscal_period="FY",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            filing_date=date(2025, 2, 1),
        ),
    )


def _publish_revenue_snapshot(
    connection: sqlite3.Connection,
) -> tuple[int, PublishedCompanyMetricSnapshot]:
    company_id, raw_fact, metric = _seed_revenue_metric(connection)
    published = publish_company_metric_snapshot(
        stage=StagedCompanyMetricSnapshot(
            company_id=company_id,
            raw_fact_ids=(raw_fact.raw_fact_id,),
            metrics=(metric,),
            target_statuses=(
                SnapshotTargetStatus(
                    statement_type="income_statement",
                    metric_name="revenue",
                    period_type="duration",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    status="mapped",
                ),
            ),
            component_versions=(
                SnapshotComponentVersion(
                    component="mapping_policy",
                    version="1",
                ),
            ),
            completed_at=datetime(
                2026,
                7,
                27,
                12,
                0,
                tzinfo=timezone.utc,
            ),
        ),
        connection=connection,
    )
    return company_id, published
