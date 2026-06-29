"""Gemini-backed hard-industry classification from 10-K Item 1 Business."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from src.analyze.prompts import (
    INDUSTRY_CLASSIFICATION_PROMPT_VERSION,
    build_industry_classification_prompt,
)
from src.processing.company_industry_labels import (
    CompanyIndustryLabelAssignment,
    LABEL_STATUS_ASSIGNED,
    LABEL_STATUS_IGNORED,
    validate_industry_labels,
)

GEMINI_INDUSTRY_ASSIGNMENT_SOURCE = "gemini_item1_business_classification"
GEMINI_INDUSTRY_CLASSIFIER_VERSION = "gemini_item1_business_v1"
DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL = "gemini-2.5-flash"
DEFAULT_MIN_INDUSTRY_CLASSIFICATION_CONFIDENCE = 0.70
MAX_BUSINESS_SECTION_CHARACTERS = 60_000
SOURCE_ACCESSION_EVIDENCE_PREFIX = "Source accession: "

IndustryJsonGenerator = Callable[[str, type[BaseModel], str], object]


class GeminiIndustryClassificationUnavailable(RuntimeError):
    """Raised when Gemini classification cannot run in the current environment."""


class IndustryClassificationResponse(BaseModel):
    """Structured Gemini response for hard-industry classification."""

    labels: list[str] = Field(
        default_factory=list,
        description="Hard industry labels selected from the allowed label enum.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classifier confidence from 0.0 to 1.0.",
    )
    reason: str = Field(
        min_length=1,
        description="Short explanation grounded in 10-K Item 1 Business.",
    )
    evidence_quotes: list[str] = Field(
        default_factory=list,
        description="Short supporting quotes or paraphrases from Item 1 Business.",
    )

    @field_validator("labels")
    @classmethod
    def normalize_labels(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(label.strip() for label in value if label and label.strip()))

    @field_validator("evidence_quotes")
    @classmethod
    def normalize_quotes(cls, value: list[str]) -> list[str]:
        return [quote.strip() for quote in value if quote and quote.strip()]


@dataclass(frozen=True)
class BusinessSectionSource:
    """The filing source used for Gemini industry classification."""

    accession_number: str
    filing_date: str
    local_path: str
    text: str


def classify_company_industry_labels(
    *,
    ticker: str,
    cik: str,
    company_name: str | None,
    business_section: BusinessSectionSource,
    sic: str | None = None,
    sic_description: str | None = None,
    api_key: str | None,
    model: str = DEFAULT_GEMINI_INDUSTRY_CLASSIFICATION_MODEL,
    generate_json: IndustryJsonGenerator | None = None,
    min_confidence: float = DEFAULT_MIN_INDUSTRY_CLASSIFICATION_CONFIDENCE,
) -> CompanyIndustryLabelAssignment:
    """Classify company hard-industry labels from 10-K Item 1 Business."""
    if api_key is None or not api_key.strip():
        raise GeminiIndustryClassificationUnavailable("Gemini API key is not configured")
    if not business_section.text.strip():
        raise GeminiIndustryClassificationUnavailable("10-K Item 1 Business text is empty")

    prompt = build_industry_classification_prompt(
        ticker=ticker,
        cik=cik,
        company_name=company_name,
        sic=sic,
        sic_description=sic_description,
        business_section_text=_truncate_business_text(business_section.text),
    )
    payload = (
        generate_json(prompt, IndustryClassificationResponse, model)
        if generate_json is not None
        else _generate_gemini_json(
            prompt=prompt,
            response_schema=IndustryClassificationResponse,
            model=model,
            api_key=api_key,
        )
    )
    response = _coerce_classification_response(payload)
    return _assignment_from_response(
        response=response,
        ticker=ticker,
        cik=cik,
        model=model,
        business_section=business_section,
        min_confidence=min_confidence,
    )


def stored_label_source_accessions(evidence: tuple[str, ...]) -> tuple[str, ...]:
    """Return source accessions recorded in stored industry-label evidence."""
    accessions: list[str] = []
    for item in evidence:
        if item.startswith(SOURCE_ACCESSION_EVIDENCE_PREFIX):
            accessions.append(item.removeprefix(SOURCE_ACCESSION_EVIDENCE_PREFIX).strip())
    return tuple(accession for accession in accessions if accession)


def _generate_gemini_json(
    *,
    prompt: str,
    response_schema: type[BaseModel],
    model: str,
    api_key: str,
) -> object:
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiIndustryClassificationUnavailable(
            "google-genai is not installed; cannot run Gemini industry classification"
        ) from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        },
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return getattr(response, "text", "")


def _coerce_classification_response(payload: object) -> IndustryClassificationResponse:
    if isinstance(payload, IndustryClassificationResponse):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    if isinstance(payload, str):
        payload = json.loads(_extract_json_text(payload))
    if not isinstance(payload, dict):
        raise ValueError("Gemini industry classification returned a non-object payload")
    return IndustryClassificationResponse.model_validate(payload)


def _assignment_from_response(
    *,
    response: IndustryClassificationResponse,
    ticker: str,
    cik: str,
    model: str,
    business_section: BusinessSectionSource,
    min_confidence: float,
) -> CompanyIndustryLabelAssignment:
    evidence = _classification_evidence(
        response=response,
        model=model,
        business_section=business_section,
    )
    try:
        labels = validate_industry_labels(response.labels)
    except ValueError as exc:
        return _ignored_assignment(
            ticker=ticker,
            cik=cik,
            reason=f"Gemini returned unsupported hard industry labels: {exc}",
            evidence=evidence,
            confidence=response.confidence,
        )

    if not labels:
        return _ignored_assignment(
            ticker=ticker,
            cik=cik,
            reason="Gemini did not assign any supported hard industry label; classification ignored.",
            evidence=evidence,
            confidence=response.confidence,
        )
    if response.confidence < min_confidence:
        return _ignored_assignment(
            ticker=ticker,
            cik=cik,
            reason=(
                "Gemini hard-industry classification was below the keep "
                f"threshold {min_confidence:.2f}; low-confidence labels ignored."
            ),
            evidence=evidence,
            confidence=response.confidence,
        )

    return CompanyIndustryLabelAssignment(
        ticker=ticker.strip().upper(),
        cik=cik,
        assigned_industry_labels=labels,
        assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
        assignment_reason=response.reason.strip(),
        supporting_evidence=evidence,
        reviewed_at="",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="High-confidence Gemini label from 10-K Item 1 Business; no human approval required.",
        confidence=response.confidence,
        classifier_version=GEMINI_INDUSTRY_CLASSIFIER_VERSION,
    )


def _ignored_assignment(
    *,
    ticker: str,
    cik: str,
    reason: str,
    evidence: tuple[str, ...],
    confidence: float | None,
) -> CompanyIndustryLabelAssignment:
    return CompanyIndustryLabelAssignment(
        ticker=ticker.strip().upper(),
        cik=cik,
        assigned_industry_labels=(),
        assignment_source=GEMINI_INDUSTRY_ASSIGNMENT_SOURCE,
        assignment_reason=reason,
        supporting_evidence=evidence,
        reviewed_at="",
        label_status=LABEL_STATUS_IGNORED,
        notes="Gemini classification was ignored; no human approval step is required.",
        confidence=confidence,
        classifier_version=GEMINI_INDUSTRY_CLASSIFIER_VERSION,
    )


def _classification_evidence(
    *,
    response: IndustryClassificationResponse,
    model: str,
    business_section: BusinessSectionSource,
) -> tuple[str, ...]:
    evidence = [
        f"Prompt version: {INDUSTRY_CLASSIFICATION_PROMPT_VERSION}",
        f"Classifier version: {GEMINI_INDUSTRY_CLASSIFIER_VERSION}",
        f"Gemini model: {model}",
        f"{SOURCE_ACCESSION_EVIDENCE_PREFIX}{business_section.accession_number}",
        f"Source filing date: {business_section.filing_date}",
        f"Source path: {business_section.local_path}",
        "Source section: 10-K Item 1. Business",
        f"Confidence: {response.confidence:.2f}",
        f"Reason: {response.reason.strip()}",
    ]
    for quote in response.evidence_quotes[:5]:
        evidence.append(f"Evidence quote: {quote}")
    return tuple(evidence)


def _truncate_business_text(text: str) -> str:
    normalized = text.strip()
    if len(normalized) <= MAX_BUSINESS_SECTION_CHARACTERS:
        return normalized
    return normalized[:MAX_BUSINESS_SECTION_CHARACTERS] + "\n[Truncated for Gemini classification input.]"


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return stripped
