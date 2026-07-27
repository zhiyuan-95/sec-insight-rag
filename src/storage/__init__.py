"""Local persistence package."""

from src.storage.company_repository import CompanyRecord, CompanyRepository
from src.storage.company_metric_snapshots_repository import (
    ArchivedFinancialMetric,
    CompanyMetricSnapshotRepository,
    MetricInvalidation,
    PublishedCompanyMetricSnapshot,
    SnapshotComponentVersion,
    SnapshotTargetKey,
    SnapshotTargetStatus,
)
from src.storage.concept_mappings_repository import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_SCOPE_GLOBAL,
    MAPPING_SCOPE_INDUSTRY,
    MAPPING_STATUS_APPROVED,
    ConceptMappingRecord,
    ConceptMappingRepository,
)
from src.storage.database import connect_sqlite, initialize_database
from src.storage.facts_repository import (
    RawFactConflictEvidence,
    RawFactRepository,
    StoredRawFact,
)
from src.storage.filings_repository import FilingRecord, FilingRepository
from src.storage.industry_labels_repository import (
    CompanyIndustryLabelRepository,
    IndustryLabelSnapshotConflictError,
    StoredCompanyIndustryLabel,
    StoredFiscalPeriodIndustryLabelSnapshot,
)
from src.storage.indicators_repository import FinancialIndicatorRepository
from src.storage.metrics_repository import FinancialMetric, FinancialMetricRepository
from src.storage.mapping_shadow_candidates_repository import (
    MappingShadowCandidateRepository,
    StoredMappingShadowCandidate,
)
from src.storage.retrieval_repository import (
    FilingChunk,
    RetrievalIndexState,
    RetrievalRepository,
    StoredFilingChunk,
)
from src.storage.recovery_applications_repository import (
    RecoveryApplicationConflictError,
    RecoveryApplicationRepository,
    StoredRecoveryApplication,
)
from src.storage.semantic_recommendations_repository import (
    SemanticRecommendationConflictError,
    SemanticRecommendationRepository,
)

__all__ = [
    "CompanyRecord",
    "CompanyRepository",
    "ArchivedFinancialMetric",
    "CompanyMetricSnapshotRepository",
    "MetricInvalidation",
    "CompanyIndustryLabelRepository",
    "IndustryLabelSnapshotConflictError",
    "ConceptMappingRecord",
    "ConceptMappingRepository",
    "FilingRecord",
    "FilingRepository",
    "FinancialIndicatorRepository",
    "FinancialMetric",
    "FinancialMetricRepository",
    "FilingChunk",
    "MAPPING_SCOPE_COMPANY",
    "MAPPING_SCOPE_GLOBAL",
    "MAPPING_SCOPE_INDUSTRY",
    "MAPPING_STATUS_APPROVED",
    "MappingShadowCandidateRepository",
    "RawFactRepository",
    "RawFactConflictEvidence",
    "RetrievalIndexState",
    "RetrievalRepository",
    "RecoveryApplicationConflictError",
    "RecoveryApplicationRepository",
    "SemanticRecommendationConflictError",
    "SemanticRecommendationRepository",
    "StoredRawFact",
    "StoredCompanyIndustryLabel",
    "StoredFiscalPeriodIndustryLabelSnapshot",
    "StoredFilingChunk",
    "StoredRecoveryApplication",
    "StoredMappingShadowCandidate",
    "PublishedCompanyMetricSnapshot",
    "SnapshotComponentVersion",
    "SnapshotTargetKey",
    "SnapshotTargetStatus",
    "connect_sqlite",
    "initialize_database",
]
