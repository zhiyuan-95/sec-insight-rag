"""Source-controlled hard industry label assignments for companies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

HARD_INDUSTRY_LABELS = (
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Information Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
)

LABEL_STATUS_ASSIGNED = "assigned"
LABEL_STATUS_NEEDS_REVIEW = "needs_label_review"
LABEL_STATUS_IGNORED = "ignored"


@dataclass(frozen=True)
class CompanyIndustryLabelAssignment:
    """Auditable hard industry labels for one company."""

    ticker: str
    cik: str
    assigned_industry_labels: tuple[str, ...]
    assignment_source: str
    assignment_reason: str
    supporting_evidence: tuple[str, ...]
    reviewed_at: str
    label_status: str
    notes: str = ""
    confidence: float | None = None
    classifier_version: str | None = None


_ASSIGNMENTS: tuple[CompanyIndustryLabelAssignment, ...] = (
    CompanyIndustryLabelAssignment(
        ticker="TSLA",
        cik="0001318605",
        assigned_industry_labels=("Consumer Discretionary", "Industrials", "Energy"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason=(
            "Tesla reports automotive operations, manufacturing-heavy operations, "
            "and energy generation/storage activities."
        ),
        supporting_evidence=(
            "SEC SIC 3711: Motor Vehicles and Passenger Car Bodies",
            "Company filings describe automotive, energy generation, and energy storage products.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 experiment assignment.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="MSFT",
        cik="0000789019",
        assigned_industry_labels=("Information Technology", "Communication Services"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason=(
            "Microsoft reports software, cloud, devices, gaming, professional network, "
            "and search/advertising activities."
        ),
        supporting_evidence=(
            "SEC SIC 7372: Services-Prepackaged Software",
            "Company filings describe cloud, productivity, operating system, gaming, and search services.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 experiment assignment.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="AAPL",
        cik="0000320193",
        assigned_industry_labels=("Information Technology", "Consumer Discretionary"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Apple reports technology products, services, and consumer device sales.",
        supporting_evidence=(
            "SEC SIC 3571: Electronic Computers",
            "Company filings describe iPhone, Mac, iPad, wearables, services, and related product sales.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="AMZN",
        cik="0001018724",
        assigned_industry_labels=("Consumer Discretionary", "Information Technology"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Amazon reports online retail, marketplace, subscription, advertising, and cloud services.",
        supporting_evidence=(
            "SEC SIC 5961: Retail-Catalog and Mail-Order Houses",
            "Company filings describe North America, International, and AWS segments.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="GOOGL",
        cik="0001652044",
        assigned_industry_labels=("Communication Services", "Information Technology"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Alphabet reports search, advertising, platforms, cloud, and other technology activities.",
        supporting_evidence=(
            "SEC SIC 7370: Services-Computer Programming, Data Processing, Etc.",
            "Company filings describe Google Services, Google Cloud, and Other Bets.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="META",
        cik="0001326801",
        assigned_industry_labels=("Communication Services", "Information Technology"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Meta reports social platforms, advertising, and metaverse/AI technology activities.",
        supporting_evidence=(
            "SEC SIC 7370: Services-Computer Programming, Data Processing, Etc.",
            "Company filings describe Family of Apps and Reality Labs.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="NVDA",
        cik="0001045810",
        assigned_industry_labels=("Information Technology",),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="NVIDIA reports accelerated computing, GPUs, networking, systems, and software.",
        supporting_evidence=(
            "SEC SIC 3674: Semiconductors and Related Devices",
            "Company filings describe compute, networking, graphics, and AI infrastructure products.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="JPM",
        cik="0000019617",
        assigned_industry_labels=("Financials",),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="JPMorgan Chase reports banking, lending, markets, payments, and asset management activities.",
        supporting_evidence=(
            "SEC SIC 6021: National Commercial Banks",
            "Company filings describe Consumer and Community Banking, Corporate and Investment Bank, Commercial Banking, and Asset and Wealth Management.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="XOM",
        cik="0000034088",
        assigned_industry_labels=("Energy", "Materials"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Exxon Mobil reports oil and gas operations and chemical/materials activities.",
        supporting_evidence=(
            "SEC SIC 2911: Petroleum Refining",
            "Company filings describe upstream, energy products, chemical products, and specialty products.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="NEE",
        cik="0000753308",
        assigned_industry_labels=("Utilities", "Energy"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="NextEra Energy reports regulated utility and energy generation activities.",
        supporting_evidence=(
            "SEC SIC 4911: Electric Services",
            "Company filings describe FPL and NextEra Energy Resources.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="PLD",
        cik="0001045609",
        assigned_industry_labels=("Real Estate",),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Prologis reports logistics real estate ownership and operations.",
        supporting_evidence=(
            "SEC SIC 6798: Real Estate Investment Trusts",
            "Company filings describe logistics facilities and real estate operations.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="JNJ",
        cik="0000200406",
        assigned_industry_labels=("Health Care",),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Johnson & Johnson reports pharmaceutical and medical technology activities.",
        supporting_evidence=(
            "SEC SIC 2834: Pharmaceutical Preparations",
            "Company filings describe Innovative Medicine and MedTech operations.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
    CompanyIndustryLabelAssignment(
        ticker="WMT",
        cik="0000104169",
        assigned_industry_labels=("Consumer Staples", "Consumer Discretionary"),
        assignment_source="manual_source_controlled_registry",
        assignment_reason="Walmart reports grocery, general merchandise, ecommerce, and membership activities.",
        supporting_evidence=(
            "SEC SIC 5331: Retail-Variety Stores",
            "Company filings describe Walmart U.S., Walmart International, and Sam's Club.",
        ),
        reviewed_at="2026-06-18",
        label_status=LABEL_STATUS_ASSIGNED,
        notes="Initial Plan 2.5.1 registry seed.",
    ),
)

_ASSIGNMENTS_BY_TICKER = {assignment.ticker: assignment for assignment in _ASSIGNMENTS}
_ASSIGNMENTS_BY_CIK = {assignment.cik: assignment for assignment in _ASSIGNMENTS}


def industry_label_assignments_for_company(
    ticker: str | None,
    cik: str | None,
    *,
    sic: str | None = None,
    sic_description: str | None = None,
    observed_concepts: Iterable[str] = (),
) -> CompanyIndustryLabelAssignment:
    """Return the source-controlled label assignment, or a review placeholder."""
    normalized_ticker = (ticker or "").strip().upper()
    normalized_cik = _normalize_cik(cik)
    assignment = _ASSIGNMENTS_BY_TICKER.get(normalized_ticker)
    if assignment is None and normalized_cik is not None:
        assignment = _ASSIGNMENTS_BY_CIK.get(normalized_cik)
    if assignment is not None:
        return assignment
    return CompanyIndustryLabelAssignment(
        ticker=normalized_ticker or "UNKNOWN",
        cik=normalized_cik or "",
        assigned_industry_labels=(),
        assignment_source="not_assigned",
        assignment_reason="No source-controlled hard industry label assignment exists for this company.",
        supporting_evidence=industry_label_evidence_for_company(
            sic=sic,
            sic_description=sic_description,
            observed_concepts=observed_concepts,
        ),
        reviewed_at="",
        label_status=LABEL_STATUS_NEEDS_REVIEW,
        notes="Add this company to the registry before treating industry-specific target coverage as complete.",
    )


def industry_label_evidence_for_company(
    *,
    sic: str | None,
    sic_description: str | None,
    observed_concepts: Iterable[str] = (),
) -> tuple[str, ...]:
    """Collect review evidence without assigning labels automatically."""
    evidence: list[str] = []
    if sic:
        evidence.append(f"SEC SIC: {sic}")
    if sic_description:
        evidence.append(f"SEC SIC description: {sic_description}")
    observed = tuple(sorted({concept for concept in observed_concepts if concept}))
    if observed:
        preview = ", ".join(observed[:12])
        suffix = f"; +{len(observed) - 12} more observed concepts" if len(observed) > 12 else ""
        evidence.append(f"Observed XBRL concept sample for review only: {preview}{suffix}")
    if not evidence:
        evidence.append("No SIC or observed concept evidence available for label review.")
    return tuple(evidence)


def validate_industry_labels(industry_labels: Iterable[str]) -> tuple[str, ...]:
    """Validate and normalize hard industry labels."""
    labels = tuple(dict.fromkeys(label.strip() for label in industry_labels if label and label.strip()))
    unknown = sorted(set(labels) - set(HARD_INDUSTRY_LABELS))
    if unknown:
        raise ValueError(f"Unknown hard industry labels: {', '.join(unknown)}")
    return labels


def list_company_industry_label_assignments() -> tuple[CompanyIndustryLabelAssignment, ...]:
    """Return all source-controlled assignments."""
    return _ASSIGNMENTS


def _normalize_cik(cik: str | None) -> str | None:
    if cik is None:
        return None
    text = str(cik).strip()
    if not text:
        return None
    return text.zfill(10) if text.isdigit() and len(text) <= 10 else text
