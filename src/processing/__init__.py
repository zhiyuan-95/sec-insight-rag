"""XBRL processing package."""

from src.processing.active_window import active_accessions_for_facts, active_period_keys, is_fact_in_active_window
from src.processing.base_metrics import (
    BASE_METRIC_MAPPINGS,
    BaseMetricRecord,
    map_raw_facts_to_base_metrics,
)
from src.processing.concepts import COMMON_GAAP_CONCEPTS, DEFAULT_FORMS, SUPPORTED_REPORT_FORMS
from src.processing.errors import XbrlPayloadError, XbrlProcessingError
from src.processing.periods import classify_period, parse_sec_date, validate_period
from src.processing.xbrl_normalizer import NormalizedFact, find_duplicate_facts, normalize_companyfacts, normalize_fact_entry

__all__ = [
    "BASE_METRIC_MAPPINGS",
    "COMMON_GAAP_CONCEPTS",
    "DEFAULT_FORMS",
    "SUPPORTED_REPORT_FORMS",
    "BaseMetricRecord",
    "NormalizedFact",
    "XbrlPayloadError",
    "XbrlProcessingError",
    "active_accessions_for_facts",
    "active_period_keys",
    "classify_period",
    "find_duplicate_facts",
    "is_fact_in_active_window",
    "map_raw_facts_to_base_metrics",
    "normalize_companyfacts",
    "normalize_fact_entry",
    "parse_sec_date",
    "validate_period",
]
