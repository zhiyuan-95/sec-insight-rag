"""Local persistence package."""

from src.storage.company_repository import CompanyRecord, CompanyRepository
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
from src.storage.retrieval_repository import (
    FilingChunk,
    RetrievalIndexState,
    RetrievalRepository,
    StoredFilingChunk,
)

__all__ = [
    "CompanyRecord",
    "CompanyRepository",
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
    "RawFactRepository",
    "RawFactConflictEvidence",
    "RetrievalIndexState",
    "RetrievalRepository",
    "StoredRawFact",
    "StoredCompanyIndustryLabel",
    "StoredFiscalPeriodIndustryLabelSnapshot",
    "StoredFilingChunk",
    "connect_sqlite",
    "initialize_database",
]
