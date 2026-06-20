"""Local SEC filing evidence retrieval."""

from src.retrieval.errors import (
    ActiveFilingsNotFoundError,
    EmptyFilingTextError,
    FilingParseError,
    FilingSourceMissingError,
    InvalidRetrievalQueryError,
    RetrievalCompanyNotFoundError,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalIndexCorruptError,
    RetrievalIndexMismatchError,
    RetrievalIndexNotFoundError,
)
from src.retrieval.models import FilingIndexSummary, IndexSyncResult, RetrievedEvidence
from src.retrieval.service import (
    delete_company_retrieval_artifacts,
    retrieve_filing_evidence,
    sync_company_retrieval_index,
)

__all__ = [
    "ActiveFilingsNotFoundError",
    "EmptyFilingTextError",
    "FilingIndexSummary",
    "FilingParseError",
    "FilingSourceMissingError",
    "IndexSyncResult",
    "InvalidRetrievalQueryError",
    "RetrievedEvidence",
    "RetrievalCompanyNotFoundError",
    "RetrievalConfigurationError",
    "RetrievalError",
    "RetrievalIndexCorruptError",
    "RetrievalIndexMismatchError",
    "RetrievalIndexNotFoundError",
    "delete_company_retrieval_artifacts",
    "retrieve_filing_evidence",
    "sync_company_retrieval_index",
]
