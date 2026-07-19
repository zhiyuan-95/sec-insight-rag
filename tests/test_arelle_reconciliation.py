from datetime import date
from decimal import Decimal

from src.processing.arelle_reconciliation import reconcile_arelle_with_companyfacts
from src.processing.arelle_records import (
    ArelleFilingResult,
    ContextKey,
    DimensionValue,
    ExtractedFact,
    QNameKey,
    UnitKey,
)
from src.processing.xbrl_normalizer import NormalizedFact


ACCESSION = "0000000000-24-000001"


def _arelle_fact(
    concept: str,
    value: str,
    *,
    namespace: str = "https://fasb.org/us-gaap/2024",
    prefix: str = "us-gaap",
    context_id: str = "c1",
    dimensions: tuple[DimensionValue, ...] = (),
) -> ExtractedFact:
    return ExtractedFact(
        concept_key=QNameKey(namespace, concept, prefix),
        context_key=ContextKey(
            context_id=context_id,
            entity_scheme="https://www.sec.gov/CIK",
            entity_identifier="0000000000",
            period_type="duration",
            start_date="2024-01-01",
            end_date="2024-12-31",
            dimensions=dimensions,
        ),
        value=value,
        value_raw=value,
        nil=False,
        unit_key=UnitKey((QNameKey("http://www.xbrl.org/2003/iso4217", "USD"),)),
    )


def _company_fact(
    concept: str,
    value: str,
    *,
    accession: str = ACCESSION,
    dimensions: tuple[tuple[str, str], ...] = (),
) -> NormalizedFact:
    return NormalizedFact(
        cik="0000000000",
        entity_name="Example",
        taxonomy="us-gaap",
        concept=concept,
        label=None,
        description=None,
        unit="USD",
        value_raw=value,
        value=Decimal(value),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="duration",
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        filed_date=date(2025, 2, 1),
        accession_number=accession,
        frame=None,
        source="sec_companyfacts",
        dimensions=dimensions,
        is_consolidated=not dimensions,
    )


def test_reconciliation_matches_decimal_values_by_taxonomy_family() -> None:
    result = ArelleFilingResult(
        accession_number=ACCESSION,
        status="complete",
        facts=(_arelle_fact("Revenue", "100.0"),),
    )

    summary = reconcile_arelle_with_companyfacts(
        result,
        [_company_fact("Revenue", "100")],
    )

    assert summary.exact_matches == 1
    assert summary.value_conflicts == 0
    assert summary.arelle_facts_considered == 1
    assert summary.companyfacts_facts_considered == 1


def test_reconciliation_does_not_merge_different_taxonomy_families() -> None:
    result = ArelleFilingResult(
        accession_number=ACCESSION,
        status="complete",
        facts=(
            _arelle_fact(
                "Revenue",
                "100",
                namespace="https://example.test/ext/2024",
                prefix="example",
            ),
        ),
    )

    summary = reconcile_arelle_with_companyfacts(
        result,
        [_company_fact("Revenue", "100")],
    )

    assert summary.exact_matches == 0
    assert summary.arelle_only_facts == 1
    assert summary.companyfacts_only_facts == 1


def test_reconciliation_reports_conflict_without_selecting_a_winner() -> None:
    result = ArelleFilingResult(
        accession_number=ACCESSION,
        status="complete",
        facts=(_arelle_fact("Revenue", "100"),),
    )

    summary = reconcile_arelle_with_companyfacts(
        result,
        [_company_fact("Revenue", "101")],
    )

    assert summary.value_conflicts == 1
    assert summary.conflicts[0].arelle_value == "100"
    assert summary.conflicts[0].companyfacts_value == "101"


def test_reconciliation_keeps_duplicates_and_dimensional_facts_visible() -> None:
    dimension = DimensionValue(
        dimension=QNameKey("https://example.test", "RegionAxis"),
        member=QNameKey("https://example.test", "NorthAmericaMember"),
    )
    result = ArelleFilingResult(
        accession_number=ACCESSION,
        status="complete",
        facts=(
            _arelle_fact("Revenue", "100", context_id="c1"),
            _arelle_fact("Revenue", "100", context_id="c2"),
            _arelle_fact("Revenue", "80", context_id="c3", dimensions=(dimension,)),
        ),
    )

    summary = reconcile_arelle_with_companyfacts(
        result,
        [
            _company_fact("Revenue", "100"),
            _company_fact("Revenue", "80", dimensions=(("RegionAxis", "NorthAmerica"),)),
        ],
    )

    assert summary.ambiguous_keys == 1
    assert summary.exact_matches == 0
    assert summary.arelle_facts_considered == 2
    assert summary.companyfacts_facts_considered == 1


def test_reconciliation_filters_other_accessions_and_counts_source_only_facts() -> None:
    result = ArelleFilingResult(
        accession_number=ACCESSION,
        status="complete",
        facts=(
            _arelle_fact("Revenue", "100"),
            _arelle_fact("Assets", "200"),
        ),
    )

    summary = reconcile_arelle_with_companyfacts(
        result,
        [
            _company_fact("Revenue", "100", accession="0000000000-23-000002"),
            _company_fact("Liabilities", "50"),
        ],
    )

    assert summary.arelle_only_facts == 2
    assert summary.companyfacts_only_facts == 1
    assert summary.companyfacts_facts_considered == 1
