import pytest

from src.processing.company_industry_labels import (
    LABEL_STATUS_ASSIGNED,
    LABEL_STATUS_NEEDS_REVIEW,
    industry_label_assignments_for_company,
    validate_industry_labels,
)
from src.processing.mapping_catalog import (
    COMMON_BASE_LABEL,
    mapping_candidates_by_concept,
    target_facts_for_industry_labels,
)


def test_known_company_labels_are_resolved_by_normalized_ticker_and_cik() -> None:
    by_ticker = industry_label_assignments_for_company(" msft ", None)
    by_cik = industry_label_assignments_for_company(None, "789019")

    assert by_ticker == by_cik
    assert by_ticker.label_status == LABEL_STATUS_ASSIGNED
    assert by_ticker.assigned_industry_labels == (
        "Information Technology",
        "Communication Services",
    )


def test_unknown_company_returns_review_placeholder_with_supporting_evidence() -> None:
    assignment = industry_label_assignments_for_company(
        "new",
        "123",
        sic="9999",
        sic_description="Example industry",
        observed_concepts=("ZetaConcept", "AlphaConcept", "AlphaConcept"),
    )

    assert assignment.ticker == "NEW"
    assert assignment.cik == "0000000123"
    assert assignment.label_status == LABEL_STATUS_NEEDS_REVIEW
    assert assignment.assigned_industry_labels == ()
    assert assignment.supporting_evidence == (
        "SEC SIC: 9999",
        "SEC SIC description: Example industry",
        "Observed XBRL concept sample for review only: AlphaConcept, ZetaConcept",
    )


def test_validate_industry_labels_deduplicates_and_rejects_unknown_values() -> None:
    assert validate_industry_labels(
        ("Energy", " Energy ", "Materials")
    ) == ("Energy", "Materials")

    with pytest.raises(ValueError, match="Unknown hard industry labels: Banking"):
        validate_industry_labels(("Banking",))


def test_industry_targets_extend_common_targets_without_duplicate_mappings() -> None:
    targets = target_facts_for_industry_labels(("Energy",))
    mapping_keys = {
        (target.taxonomy, target.raw_concept, target.internal_metric_name, target.statement_type)
        for target in targets
    }

    assert len(mapping_keys) == len(targets)
    assert any(target.industry_label == COMMON_BASE_LABEL for target in targets)
    assert any("Energy" in target.industry_label for target in targets)


def test_mapping_candidates_prefer_common_mapping_for_shared_concepts() -> None:
    candidates = mapping_candidates_by_concept(("Energy",))

    assert candidates["Revenues"].internal_metric_name == "revenue"
    assert candidates["Revenues"].industry_label == COMMON_BASE_LABEL
    assert "AssetRetirementObligation" in candidates
