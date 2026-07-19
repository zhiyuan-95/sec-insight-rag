from src.processing.arelle_precedence import (
    DEGRADED_ACCESSION,
    DUPLICATE_FACT,
    NIL_FACT,
    apply_arelle_accession_precedence,
)
from src.processing.arelle_records import (
    ArelleFilingResult,
    ContextKey,
    ExtractedFact,
    QNameKey,
    UnitKey,
)


def _fact(
    concept: str,
    value: str | None,
    *,
    source_line: int = 10,
    start_date: str = "2024-01-01",
    end_date: str = "2024-12-31",
) -> ExtractedFact:
    return ExtractedFact(
        concept_key=QNameKey("https://fasb.org/us-gaap/2024", concept, "us-gaap"),
        context_key=ContextKey(
            context_id=f"c-{source_line}",
            entity_scheme="https://www.sec.gov/CIK",
            entity_identifier="0000000001",
            period_type="duration",
            start_date=start_date,
            end_date=end_date,
        ),
        value=value,
        value_raw=value,
        nil=value is None,
        unit_key=UnitKey((QNameKey("http://www.xbrl.org/2003/iso4217", "USD"),)),
        source_document="filing/example.htm",
        source_line=source_line,
    )


def _result(
    accession: str,
    filing_date: str,
    *facts: ExtractedFact,
    form: str = "10-K",
    status: str = "complete",
) -> ArelleFilingResult:
    return ArelleFilingResult(
        accession_number=accession,
        status=status,
        cik="0000000001",
        form=form,
        filing_date=filing_date,
        facts=facts,
    )


def test_later_complete_amendment_replaces_same_fact_identity() -> None:
    original = _result("0000000001-25-000001", "2025-02-01", _fact("Revenue", "100"))
    amendment = _result(
        "0000000001-25-000002",
        "2025-02-10",
        _fact("Revenue", "101"),
        form="10-K/A",
    )

    precedence = apply_arelle_accession_precedence([original, amendment])

    assert len(precedence.selected) == 1
    assert precedence.selected[0].accession_number == amendment.accession_number
    assert precedence.selected[0].fact.value == "101"


def test_amendment_omission_does_not_erase_older_fact() -> None:
    original = _result(
        "0000000001-25-000001",
        "2025-02-01",
        _fact("Revenue", "100"),
        _fact("Assets", "200"),
    )
    amendment = _result(
        "0000000001-25-000002",
        "2025-02-10",
        _fact("Revenue", "101"),
        form="10-K/A",
    )

    precedence = apply_arelle_accession_precedence([original, amendment])

    selected = {item.fact.concept_key.local_name: item for item in precedence.selected}
    assert selected["Revenue"].accession_number == amendment.accession_number
    assert selected["Assets"].accession_number == original.accession_number


def test_nil_or_degraded_amendment_cannot_replace_complete_value() -> None:
    original = _result("0000000001-25-000001", "2025-02-01", _fact("Revenue", "100"))
    nil_amendment = _result(
        "0000000001-25-000002",
        "2025-02-10",
        _fact("Revenue", None),
        form="10-K/A",
    )
    degraded = _result(
        "0000000001-25-000003",
        "2025-02-11",
        _fact("Revenue", "102"),
        form="10-K/A",
        status="degraded",
    )

    precedence = apply_arelle_accession_precedence(
        [original, nil_amendment, degraded]
    )

    assert precedence.selected[0].accession_number == original.accession_number
    flags = {item.accession_number: item.quality_flags for item in precedence.quarantined}
    assert NIL_FACT in flags[nil_amendment.accession_number]
    assert DEGRADED_ACCESSION in flags[degraded.accession_number]


def test_duplicate_occurrences_are_quarantined_with_lowest_line_representative() -> None:
    duplicate = _result(
        "0000000001-25-000001",
        "2025-02-01",
        _fact("Revenue", "101", source_line=20),
        _fact("Revenue", "100", source_line=10),
    )

    precedence = apply_arelle_accession_precedence([duplicate])

    assert precedence.selected == ()
    assert precedence.quarantined[0].occurrence_count == 2
    assert precedence.quarantined[0].fact.value == "100"
    assert DUPLICATE_FACT in precedence.quarantined[0].quality_flags


def test_annual_and_quarterly_form_families_never_replace_each_other() -> None:
    annual = _result("0000000001-25-000001", "2025-02-01", _fact("Revenue", "100"))
    quarterly = _result(
        "0000000001-25-000002",
        "2025-02-10",
        _fact("Revenue", "25"),
        form="10-Q",
    )

    precedence = apply_arelle_accession_precedence([annual, quarterly])

    assert len(precedence.selected) == 2
    assert {item.form for item in precedence.selected} == {"10-K", "10-Q"}
