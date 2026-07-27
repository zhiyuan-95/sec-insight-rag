"""Thin persistence workflow for period-specific recovery applications."""

from __future__ import annotations

from src.processing.recovery_applications import (
    RECOVERY_APPLICATION_SUCCEEDED,
    RecoveryApplication,
    recovery_metric_source_accession,
)
from src.processing.company_identity import same_cik
from src.storage.company_repository import CompanyRepository
from src.storage.metrics_repository import (
    METRIC_ORIGIN_AFFIRMATIVE_ZERO_RECOVERY,
    METRIC_ORIGIN_FORMULA_RECOVERY,
    FinancialMetric,
    FinancialMetricRepository,
)
from src.storage.recovery_applications_repository import (
    RecoveryApplicationRepository,
    StoredRecoveryApplication,
)


def persist_recovery_applications(
    *,
    applications: tuple[RecoveryApplication, ...],
    metric_company_id: int,
    application_repository: RecoveryApplicationRepository,
    metric_repository: FinancialMetricRepository,
) -> tuple[StoredRecoveryApplication, ...]:
    """Persist applications and publish metrics only for successful proofs."""
    if application_repository.connection is not metric_repository.connection:
        raise ValueError(
            "application and metric repositories must share one connection"
        )
    connection = application_repository.connection
    company = CompanyRepository(connection).get_by_id(metric_company_id)
    if company is None or any(
        not same_cik(company.cik, application.company_id)
        for application in applications
    ):
        raise ValueError(
            "metric company does not match recovery application"
        )
    stored: list[StoredRecoveryApplication] = []
    try:
        for application in applications:
            record = application_repository.insert(
                application,
                commit=False,
            )
            stored.append(record)
            if application.status != RECOVERY_APPLICATION_SUCCEEDED:
                continue
            metric_repository.upsert_metrics(
                [
                    _financial_metric(
                        application,
                        recovery_application_id=(
                            record.recovery_application_id
                        ),
                        metric_company_id=metric_company_id,
                    )
                ],
                commit=False,
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return tuple(stored)


def _financial_metric(
    application: RecoveryApplication,
    *,
    recovery_application_id: int,
    metric_company_id: int,
) -> FinancialMetric:
    if (
        application.value_numeric is None
        or application.unit is None
        or application.period_type is None
        or not application.source_accession_numbers
    ):
        raise ValueError(
            "successful recovery application lacks metric evidence"
        )
    origin = (
        METRIC_ORIGIN_FORMULA_RECOVERY
        if application.decision == "formula"
        else METRIC_ORIGIN_AFFIRMATIVE_ZERO_RECOVERY
        if application.decision == "zero"
        else None
    )
    if origin is None:
        raise ValueError(
            f"unsupported successful recovery decision: {application.decision}"
        )
    return FinancialMetric(
        company_id=metric_company_id,
        accession_number=recovery_metric_source_accession(application),
        raw_fact_id=None,
        origin=origin,
        recovery_application_id=recovery_application_id,
        statement_type=application.statement_type,
        metric_name=application.target_metric_name,
        value_numeric=application.value_numeric,
        value_raw=str(application.value_numeric),
        unit=application.unit,
        period_type=application.period_type,
        fiscal_year=application.fiscal_year,
        fiscal_period=application.fiscal_period,
        start_date=application.start_date,
        end_date=application.end_date,
        filing_date=application.filing_date,
        is_active_window=True,
    )
