"""XBRL processing package."""

from src.processing.active_window import (
    active_accessions_for_facts,
    active_period_keys,
    active_period_keys_from_periods,
    is_fact_in_active_window,
)
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
from src.processing.errors import InlineXbrlExtractionError, XbrlPayloadError, XbrlProcessingError
from src.processing.inline_xbrl import (
    INLINE_XBRL_SOURCE,
    InlineXbrlExtractionResult,
    normalize_inline_xbrl_model,
)
from src.processing.mapping_catalog import (
    COMMON_BASE_LABEL,
    IndustryFactTarget,
    IndustryLabelDefinition,
    STATUS_FOUND_MAPPED_ALTERNATE,
    mapping_candidates_by_concept,
    mapping_candidates_by_key,
    target_facts_for_industry_labels,
)
from src.processing.metric_coverage import (
    METRIC_COVERAGE_APPROVED_ALTERNATE,
    METRIC_COVERAGE_MAPPED,
    METRIC_COVERAGE_NEEDS_LLM_RESOLUTION,
    METRIC_COVERAGE_NO_EVIDENCE,
    REVIEW_ACTION_LLM_CHOICE,
    REVIEW_ACTION_NO_EVIDENCE,
    REVIEW_ACTION_NONE,
    RESOLUTION_OPTION_FORMULA,
    RESOLUTION_OPTION_SEMANTIC,
    RESOLUTION_OPTION_ZERO,
    MetricCoverageResolution,
    metric_coverage_report_rows,
    resolve_metric_coverage,
)
from src.processing.periods import classify_period, parse_sec_date, validate_period
from src.processing.metric_targets import (
    CanonicalMetricTarget,
    TargetConceptCandidate,
    all_canonical_metric_targets,
    canonical_metric_targets,
    missing_metric_targets,
)
from src.processing.xbrl_normalizer import NormalizedFact, find_duplicate_facts, normalize_companyfacts, normalize_fact_entry

__all__ = [
    "BASE_METRIC_MAPPINGS",
    "COMMON_GAAP_CONCEPTS",
    "DEFAULT_FORMS",
    "SUPPORTED_REPORT_FORMS",
    "BaseMetricRecord",
    "CanonicalMetricTarget",
    "COMMON_BASE_LABEL",
    "NormalizedFact",
<<<<<<< HEAD
=======
    "SemanticMappingCandidate",
    "MetricCoverageResolution",
    "TargetEmbeddingPrewarmResult",
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
    "TargetConceptCandidate",
    "CompanyIndustryLabelAssignment",
    "HARD_INDUSTRY_LABELS",
    "IndustryFactTarget",
    "IndustryLabelDefinition",
    "INLINE_XBRL_SOURCE",
    "InlineXbrlExtractionError",
    "InlineXbrlExtractionResult",
    "STATUS_FOUND_MAPPED_ALTERNATE",
    "METRIC_COVERAGE_APPROVED_ALTERNATE",
    "METRIC_COVERAGE_MAPPED",
    "METRIC_COVERAGE_NEEDS_LLM_RESOLUTION",
    "METRIC_COVERAGE_NO_EVIDENCE",
    "REVIEW_ACTION_LLM_CHOICE",
    "REVIEW_ACTION_NO_EVIDENCE",
    "REVIEW_ACTION_NONE",
    "RESOLUTION_OPTION_FORMULA",
    "RESOLUTION_OPTION_SEMANTIC",
    "RESOLUTION_OPTION_ZERO",
    "XbrlPayloadError",
    "XbrlProcessingError",
    "active_accessions_for_facts",
    "active_period_keys",
    "active_period_keys_from_periods",
    "all_canonical_metric_targets",
    "canonical_metric_targets",
    "classify_period",
    "find_duplicate_facts",
    "industry_label_assignments_for_company",
    "industry_label_evidence_for_company",
    "is_fact_in_active_window",
    "mapping_candidates_by_concept",
    "mapping_candidates_by_key",
    "map_raw_facts_to_base_metrics",
    "metric_coverage_report_rows",
    "missing_metric_targets",
    "normalize_companyfacts",
    "normalize_fact_entry",
    "normalize_inline_xbrl_model",
    "parse_sec_date",
<<<<<<< HEAD
=======
    "prewarm_all_target_candidate_embeddings",
    "resolve_metric_coverage",
>>>>>>> d0cfc84 (Refine SEC Insight RAG analysis and reporting)
    "target_facts_for_industry_labels",
    "validate_period",
]
