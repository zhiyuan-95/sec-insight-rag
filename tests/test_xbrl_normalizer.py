import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.processing import XbrlPayloadError, normalize_companyfacts
from src.processing.concepts import COMMON_GAAP_CONCEPTS
from src.processing.quality import (
    AMBIGUOUS_UNIT,
    DUPLICATE_FACT,
    MISSING_ACCESSION_NUMBER,
    MISSING_END_DATE,
    MISSING_FORM,
    MISSING_VALUE,
    NON_NUMERIC_VALUE,
    UNSUPPORTED_FORM,
)


def _companyfacts_fixture() -> dict:
    return json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))


def test_normalize_companyfacts_preserves_core_fact_metadata() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture())

    revenue = next(fact for fact in facts if fact.concept == "Revenues" and fact.form == "10-Q")

    assert revenue.cik == "0000320193"
    assert revenue.entity_name == "Apple Inc."
    assert revenue.taxonomy == "us-gaap"
    assert revenue.label == "Revenue"
    assert revenue.description == "Revenue from goods and services."
    assert revenue.unit == "USD"
    assert revenue.value_raw == 94000000000
    assert revenue.value == Decimal("94000000000")
    assert revenue.start_date == date(2025, 3, 30)
    assert revenue.end_date == date(2025, 6, 28)
    assert revenue.period_type == "duration"
    assert revenue.fiscal_year == 2025
    assert revenue.fiscal_period == "Q3"
    assert revenue.filed_date == date(2025, 8, 1)
    assert revenue.accession_number == "0000320193-25-000073"
    assert revenue.frame == "CY2025Q2"
    assert revenue.source == "sec_companyfacts"


def test_normalize_companyfacts_handles_instant_facts_and_ambiguous_units() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture())

    asset = next(fact for fact in facts if fact.concept == "Assets" and fact.unit == "USD")

    assert asset.start_date is None
    assert asset.end_date == date(2025, 9, 27)
    assert asset.period_type == "instant"
    assert AMBIGUOUS_UNIT in asset.quality_flags


def test_normalize_companyfacts_filters_to_10k_and_10q_by_default() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture())

    assert {fact.form for fact in facts} == {"10-K", "10-Q"}


def test_normalize_companyfacts_keeps_all_concepts_in_default_taxonomies_by_default() -> None:
    payload = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 94000000000,
                                "start": "2025-03-30",
                                "end": "2025-06-28",
                                "fy": 2025,
                                "fp": "Q3",
                                "form": "10-Q",
                                "filed": "2025-08-01",
                                "accn": "0000320193-25-000073",
                            }
                        ]
                    },
                },
                "EarningsPerShareBasic": {
                    "label": "Basic EPS",
                    "units": {
                        "USD/shares": [
                            {
                                "val": 6.13,
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "0000320193-25-000079",
                            }
                        ]
                    },
                },
                "RareCompanySpecificConcept": {
                    "label": "Rare Concept",
                    "units": {
                        "USD": [
                            {
                                "val": 1,
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "0000320193-25-000079",
                            }
                        ]
                    },
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "label": "Shares Outstanding",
                    "units": {
                        "shares": [
                            {
                                "val": 15000000000,
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "0000320193-25-000079",
                            }
                        ]
                    },
                }
            },
        },
    }

    facts = normalize_companyfacts(payload)

    assert {fact.taxonomy for fact in facts} == {"us-gaap"}
    assert {fact.concept for fact in facts} == {
        "EarningsPerShareBasic",
        "RareCompanySpecificConcept",
        "Revenues",
    }


def test_normalize_companyfacts_can_include_all_taxonomies() -> None:
    payload = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 94000000000,
                                "start": "2025-03-30",
                                "end": "2025-06-28",
                                "fy": 2025,
                                "fp": "Q3",
                                "form": "10-Q",
                                "filed": "2025-08-01",
                                "accn": "0000320193-25-000073",
                            }
                        ]
                    },
                }
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "label": "Shares Outstanding",
                    "units": {
                        "shares": [
                            {
                                "val": 15000000000,
                                "end": "2025-09-27",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                                "accn": "0000320193-25-000079",
                            }
                        ]
                    },
                }
            },
        },
    }

    facts = normalize_companyfacts(payload, taxonomies=None)

    assert {fact.taxonomy for fact in facts} == {"dei", "us-gaap"}
    assert {fact.concept for fact in facts} == {
        "EntityCommonStockSharesOutstanding",
        "Revenues",
    }


def test_common_gaap_concepts_contains_expanded_raw_fact_allowlist_entries() -> None:
    assert {
        "ResearchAndDevelopmentExpense",
        "MarketableSecuritiesCurrent",
        "NetCashProvidedByUsedInInvestingActivities",
        "EarningsPerShareDiluted",
        "OtherComprehensiveIncomeLossNetOfTax",
    }.issubset(COMMON_GAAP_CONCEPTS)


def test_normalize_companyfacts_can_include_and_flag_unsupported_forms() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture(), forms=None)

    eight_k = next(fact for fact in facts if fact.form == "8-K")

    assert UNSUPPORTED_FORM in eight_k.quality_flags


def test_normalize_companyfacts_filters_by_requested_concepts() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture(), concepts={"Assets"})

    assert {fact.concept for fact in facts} == {"Assets"}


def test_normalize_companyfacts_flags_duplicate_facts() -> None:
    facts = normalize_companyfacts(_companyfacts_fixture())
    annual_revenues = [
        fact for fact in facts if fact.concept == "Revenues" and fact.fiscal_period == "FY"
    ]

    assert len(annual_revenues) == 2
    assert all(DUPLICATE_FACT in fact.quality_flags for fact in annual_revenues)


def test_normalize_companyfacts_flags_malformed_fact_values() -> None:
    payload = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": "not-a-number",
                                "start": "2025-01-01",
                                "end": "",
                                "fy": 2025,
                                "fp": "Q1",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "fy": 2025,
                                "fp": "Q1",
                            },
                        ]
                    },
                }
            }
        },
    }

    facts = normalize_companyfacts(payload, forms=None)

    assert NON_NUMERIC_VALUE in facts[0].quality_flags
    assert MISSING_END_DATE in facts[0].quality_flags
    assert MISSING_FORM in facts[0].quality_flags
    assert MISSING_ACCESSION_NUMBER in facts[0].quality_flags
    assert MISSING_VALUE in facts[1].quality_flags


def test_normalize_companyfacts_rejects_missing_facts_object() -> None:
    with pytest.raises(XbrlPayloadError):
        normalize_companyfacts({"cik": 320193})
