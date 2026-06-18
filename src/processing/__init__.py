"""XBRL processing package."""

from src.processing.active_window import active_accessions_for_facts, active_period_keys, is_fact_in_active_window
from src.processing.base_metrics import (
    BASE_METRIC_MAPPINGS,
    BaseMetricRecord,
    map_raw_facts_to_base_metrics,
)
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    HARD_INDUSTRY_LABELS,
    industry_label_assignments_for_company,
    industry_label_evidence_for_company,
)
from src.processing.concepts import COMMON_GAAP_CONCEPTS, DEFAULT_FORMS, SUPPORTED_REPORT_FORMS
from src.processing.errors import XbrlPayloadError, XbrlProcessingError
from src.processing.mapping_catalog import (
    COMMON_BASE_LABEL,
    IndustryFactTarget,
    IndustryLabelDefinition,
    mapping_candidates_by_concept,
    target_facts_for_industry_labels,
)
from src.processing.periods import classify_period, parse_sec_date, validate_period
from src.processing.xbrl_normalizer import NormalizedFact, find_duplicate_facts, normalize_companyfacts, normalize_fact_entry

__all__ = [
    "BASE_METRIC_MAPPINGS",
    "COMMON_GAAP_CONCEPTS",
    "DEFAULT_FORMS",
    "SUPPORTED_REPORT_FORMS",
    "BaseMetricRecord",
    "COMMON_BASE_LABEL",
    "NormalizedFact",
    "CompanyIndustryLabelAssignment",
    "HARD_INDUSTRY_LABELS",
    "IndustryFactTarget",
    "IndustryLabelDefinition",
    "XbrlPayloadError",
    "XbrlProcessingError",
    "active_accessions_for_facts",
    "active_period_keys",
    "classify_period",
    "find_duplicate_facts",
    "industry_label_assignments_for_company",
    "industry_label_evidence_for_company",
    "is_fact_in_active_window",
    "mapping_candidates_by_concept",
    "map_raw_facts_to_base_metrics",
    "normalize_companyfacts",
    "normalize_fact_entry",
    "parse_sec_date",
    "target_facts_for_industry_labels",
    "validate_period",
]
