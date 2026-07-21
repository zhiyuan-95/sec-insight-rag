import pytest

from src.analyze.industry_classification import (
    GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
    GEMINI_INDUSTRY_CLASSIFIER_VERSION,
    BusinessSectionSource,
    GeminiIndustryClassificationUnavailable,
    IndustryClassificationResponse,
    classify_company_industry_labels,
    stored_label_source_accessions,
)
from src.config.settings import DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL
from src.processing.company_industry_labels import (
    LABEL_STATUS_ASSIGNED,
    LABEL_STATUS_IGNORED,
)


def test_gemini_industry_classification_assigns_supported_labels() -> None:
    captured: dict[str, object] = {}

    def fake_generate_json(prompt: str, schema: type, model: str) -> object:
        captured["prompt"] = prompt
        captured["schema"] = schema
        captured["model"] = model
        return {
            "labels": [
                "Information Technology",
                "Information Technology",
                "Communication Services",
            ],
            "confidence": 0.91,
            "reason": "The company reports software, cloud, gaming, and advertising.",
            "evidence_quotes": ["cloud, software, gaming, and search advertising"],
        }

    assignment = classify_company_industry_labels(
        ticker="msft",
        cik="0000789019",
        company_name="Microsoft Corporation",
        sic="7372",
        sic_description="Services-Prepackaged Software",
        business_section=_business_source(),
        api_key="fake-key",
        generate_json=fake_generate_json,
    )

    assert captured["schema"] is IndustryClassificationResponse
    assert "Do not classify XBRL concepts" in str(captured["prompt"])
    assert "Information Technology" in str(captured["prompt"])
    assert captured["model"] == DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL
    assert assignment.label_status == LABEL_STATUS_ASSIGNED
    assert assignment.assignment_source == GEMINI_INDUSTRY_ASSIGNMENT_SOURCE
    assert assignment.assigned_industry_labels == (
        "Information Technology",
        "Communication Services",
    )
    assert assignment.confidence == 0.91
    assert assignment.classifier_version == GEMINI_INDUSTRY_CLASSIFIER_VERSION
    assert stored_label_source_accessions(assignment.supporting_evidence) == (
        "0000789019-25-000010",
    )


def test_gemini_industry_classification_ignores_low_confidence_labels() -> None:
    assignment = classify_company_industry_labels(
        ticker="new",
        cik="0000000123",
        company_name="Example Co.",
        business_section=_business_source(),
        api_key="fake-key",
        generate_json=lambda prompt, schema, model: {
            "labels": ["Energy"],
            "confidence": 0.52,
            "reason": "The business description is ambiguous.",
            "evidence_quotes": [],
        },
        min_confidence=0.70,
    )

    assert assignment.label_status == LABEL_STATUS_IGNORED
    assert assignment.assigned_industry_labels == ()
    assert "below the keep threshold" in assignment.assignment_reason
    assert "no human approval step is required" in assignment.notes


def test_gemini_industry_classification_ignores_unknown_label() -> None:
    assignment = classify_company_industry_labels(
        ticker="bank",
        cik="0000000456",
        company_name="Example Bank",
        business_section=_business_source(),
        api_key="fake-key",
        generate_json=lambda prompt, schema, model: {
            "labels": ["Banking"],
            "confidence": 0.92,
            "reason": "The company reports banking services.",
            "evidence_quotes": ["banking services"],
        },
    )

    assert assignment.label_status == LABEL_STATUS_IGNORED
    assert assignment.assigned_industry_labels == ()
    assert "unsupported hard industry labels" in assignment.assignment_reason
    assert "no human approval step is required" in assignment.notes


def test_gemini_industry_classification_accepts_fenced_json_text() -> None:
    assignment = classify_company_industry_labels(
        ticker="xom",
        cik="0000034088",
        company_name="Exxon Mobil Corporation",
        business_section=_business_source(),
        api_key="fake-key",
        generate_json=lambda prompt, schema, model: """
        ```json
        {
          "labels": ["Energy", "Materials"],
          "confidence": 0.95,
          "reason": "The company reports upstream energy and chemical products.",
          "evidence_quotes": ["upstream", "chemical products"]
        }
        ```
        """,
    )

    assert assignment.label_status == LABEL_STATUS_ASSIGNED
    assert assignment.assigned_industry_labels == ("Energy", "Materials")


def test_gemini_industry_classification_requires_api_key() -> None:
    with pytest.raises(GeminiIndustryClassificationUnavailable):
        classify_company_industry_labels(
            ticker="msft",
            cik="0000789019",
            company_name="Microsoft Corporation",
            business_section=_business_source(),
            api_key=None,
            generate_json=lambda prompt, schema, model: {},
        )


def _business_source() -> BusinessSectionSource:
    return BusinessSectionSource(
        accession_number="0000789019-25-000010",
        filing_date="2025-07-30",
        local_path="filings/msft.htm",
        text="The company reports software, cloud services, gaming, and advertising.",
    )
