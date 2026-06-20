"""Local persistence package."""

from src.storage.company_repository import CompanyRecord, CompanyRepository
from src.storage.concept_mappings_repository import (
    MAPPING_SCOPE_COMPANY,
    MAPPING_SCOPE_GLOBAL,
    MAPPING_SCOPE_INDUSTRY,
    MAPPING_STATUS_APPROVED,
    MAPPING_STATUS_CANDIDATE,
    MAPPING_STATUS_REJECTED,
    ConceptMappingRecord,
    ConceptMappingRepository,
)
from src.storage.database import connect_sqlite, initialize_database
from src.storage.facts_repository import RawFactRepository, StoredRawFact
from src.storage.filings_repository import FilingRecord, FilingRepository
from src.storage.industry_labels_repository import (
    CompanyIndustryLabelRepository,
    StoredCompanyIndustryLabel,
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
    "MAPPING_STATUS_CANDIDATE",
    "MAPPING_STATUS_REJECTED",
    "RawFactRepository",
    "RetrievalIndexState",
    "RetrievalRepository",
    "StoredRawFact",
    "StoredCompanyIndustryLabel",
    "StoredFilingChunk",
    "connect_sqlite",
    "initialize_database",
]
