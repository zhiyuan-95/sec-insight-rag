"""XBRL processing package."""

from src.processing.concepts import COMMON_GAAP_CONCEPTS, DEFAULT_FORMS, SUPPORTED_REPORT_FORMS
from src.processing.errors import XbrlPayloadError, XbrlProcessingError
from src.processing.periods import classify_period, parse_sec_date, validate_period
from src.processing.xbrl_normalizer import NormalizedFact, find_duplicate_facts, normalize_companyfacts, normalize_fact_entry

__all__ = [
    "COMMON_GAAP_CONCEPTS",
    "DEFAULT_FORMS",
    "SUPPORTED_REPORT_FORMS",
    "NormalizedFact",
    "XbrlPayloadError",
    "XbrlProcessingError",
    "classify_period",
    "find_duplicate_facts",
    "normalize_companyfacts",
    "normalize_fact_entry",
    "parse_sec_date",
    "validate_period",
]
