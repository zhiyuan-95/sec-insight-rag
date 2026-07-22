import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.processing import normalize_companyfacts
from src.processing.quality import DUPLICATE_FACT
from src.storage import RawFactRepository, connect_sqlite


def _normalized_facts() -> list:
    payload = json.loads(Path("data/fixtures/sec_companyfacts_sample.json").read_text(encoding="utf-8"))
    return normalize_companyfacts(payload)


def test_raw_fact_repository_creates_table_and_round_trips_facts(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    facts = _normalized_facts()

    inserted = repository.upsert_facts(facts)
    stored = repository.list_facts("0000320193")
    stored_records = repository.list_fact_records("0000320193")

    assert inserted == len(facts)
    assert all(record.raw_fact_id is not None for record in stored_records)
    assert [record.fact for record in stored_records] == stored
    assert {fact.concept for fact in stored} == {"Assets", "Revenues"}
    revenue = next(fact for fact in stored if fact.concept == "Revenues" and fact.form == "10-Q")
    assert revenue.value == Decimal("94000000000")
    assert revenue.value_raw == 94000000000
    assert revenue.quality_flags == ()


def test_raw_fact_repository_filters_by_concept(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    repository.upsert_facts(_normalized_facts())

    stored = repository.list_facts("0000320193", concepts={"Assets"})

    assert stored
    assert {fact.concept for fact in stored} == {"Assets"}


def test_raw_fact_repository_upserts_without_multiplying_rows(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    fact = _normalized_facts()[0]

    repository.upsert_facts([fact])
    repository.upsert_facts([fact])
    stored = repository.list_facts("0000320193")

    assert len(stored) == 1


def test_raw_fact_repository_preserves_matching_sources_separately(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    company_facts_observation = _normalized_facts()[0]
    arelle_observation = replace(
        company_facts_observation,
        source="sec_inline_xbrl",
    )
    later_accession_observation = replace(
        company_facts_observation,
        accession_number="0000320193-26-000001",
    )

    repository.upsert_facts(
        [
            company_facts_observation,
            arelle_observation,
            later_accession_observation,
        ]
    )
    stored = repository.list_facts("0000320193")

    assert len(stored) == 3
    assert {
        (fact.source, fact.accession_number)
        for fact in stored
    } == {
        ("sec_companyfacts", company_facts_observation.accession_number),
        ("sec_inline_xbrl", company_facts_observation.accession_number),
        ("sec_companyfacts", "0000320193-26-000001"),
    }


def test_raw_fact_repository_collapses_equivalent_occurrences_by_semantic_identity(
    tmp_path: Path,
) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    first = replace(
        _normalized_facts()[0],
        fiscal_year=2024,
        fiscal_period="FY",
        form="10-K",
        frame="CY2024",
        context_id="context-a",
        source_document="filing-a.htm",
    )
    second = replace(
        first,
        fiscal_year=2025,
        fiscal_period="Q4",
        form="10-K/A",
        frame="CY2025Q4",
        context_id="context-b",
        source_document="filing-b.htm",
    )

    repository.upsert_facts([first, second])
    records = repository.list_fact_records("0000320193")

    assert len(records) == 1
    assert records[0].occurrence_count == 2
    assert set(records[0].occurrence_references) == {
        "document=filing-a.htm|context=context-a|form=10-K|fiscal_year=2024|fiscal_period=FY|frame=CY2024",
        "document=filing-b.htm|context=context-b|form=10-K/A|fiscal_year=2025|fiscal_period=Q4|frame=CY2025Q4",
    }
    assert DUPLICATE_FACT not in records[0].fact.quality_flags


def test_raw_fact_repository_quarantines_conflicting_occurrences_with_evidence(
    tmp_path: Path,
) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    first = replace(
        _normalized_facts()[0],
        value_raw=100,
        value=Decimal("100"),
        context_id="context-a",
        source_document="filing.htm",
    )
    second = replace(
        first,
        value_raw=200,
        value=Decimal("200"),
        context_id="context-b",
    )

    repository.upsert_facts([first, second])
    records = repository.list_fact_records("0000320193")

    assert len(records) == 1
    assert records[0].occurrence_count == 2
    assert DUPLICATE_FACT in records[0].fact.quality_flags
    assert tuple(
        (
            evidence.value_raw,
            evidence.value_numeric,
            evidence.occurrence_references,
        )
        for evidence in records[0].conflict_evidence
    ) == (
        (
            100,
            Decimal("100"),
            (
                "document=filing.htm|context=context-a|form=10-K|fiscal_year=2025|fiscal_period=FY|frame=CY2025",
            ),
        ),
        (
            200,
            Decimal("200"),
            (
                "document=filing.htm|context=context-b|form=10-K|fiscal_year=2025|fiscal_period=FY|frame=CY2025",
            ),
        ),
    )


def test_raw_fact_repository_merges_new_conflict_evidence_idempotently(
    tmp_path: Path,
) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    first = replace(
        _normalized_facts()[0],
        value_raw=100,
        value=Decimal("100"),
        context_id="context-a",
    )
    second = replace(
        first,
        value_raw=200,
        value=Decimal("200"),
        context_id="context-b",
    )

    repository.upsert_facts([first])
    original_id = repository.list_fact_records("0000320193")[0].raw_fact_id
    repository.upsert_facts([second])
    repository.upsert_facts([second])
    record = repository.list_fact_records("0000320193")[0]

    assert record.raw_fact_id == original_id
    assert record.occurrence_count == 2
    assert DUPLICATE_FACT in record.fact.quality_flags
    assert {evidence.value_numeric for evidence in record.conflict_evidence} == {
        Decimal("100"),
        Decimal("200"),
    }


def test_raw_fact_repository_migrates_legacy_keys_in_place(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    cursor = connection.execute(
        """
        INSERT INTO raw_xbrl_facts (
            unique_key,
            cik,
            entity_name,
            taxonomy,
            concept,
            unit,
            value_raw,
            value_numeric,
            start_date,
            end_date,
            period_type,
            fiscal_year,
            fiscal_period,
            form,
            filed_date,
            accession_number,
            frame,
            context_id,
            dimensions_json,
            is_consolidated,
            source_document,
            identity_version,
            source,
            quality_flags,
            created_at
        ) VALUES (
            'legacy-key',
            '0000320193',
            'Apple Inc.',
            'us-gaap',
            'Revenues',
            'USD',
            '100',
            '100',
            '2024-01-01',
            '2024-12-31',
            'annual',
            2024,
            'FY',
            '10-K',
            '2025-01-31',
            '0000320193-25-000001',
            'CY2024',
            'context-a',
            '[]',
            1,
            'filing-a.htm',
            1,
            'sec_companyfacts',
            '[]',
            '2025-01-31T00:00:00+00:00'
        )
        """
    )
    connection.commit()
    legacy_id = cursor.lastrowid
    duplicate_cursor = connection.execute(
        """
        INSERT INTO raw_xbrl_facts (
            unique_key,
            cik,
            entity_name,
            taxonomy,
            concept,
            unit,
            value_raw,
            value_numeric,
            start_date,
            end_date,
            period_type,
            fiscal_year,
            fiscal_period,
            form,
            filed_date,
            accession_number,
            frame,
            context_id,
            dimensions_json,
            is_consolidated,
            source_document,
            identity_version,
            source,
            quality_flags,
            created_at
        )
        SELECT
            'legacy-key-b',
            cik,
            entity_name,
            taxonomy,
            concept,
            unit,
            value_raw,
            value_numeric,
            start_date,
            end_date,
            period_type,
            2025,
            'Q4',
            '10-K/A',
            '2025-02-14',
            accession_number,
            'CY2024Q4',
            'context-b',
            dimensions_json,
            is_consolidated,
            'filing-b.htm',
            1,
            source,
            quality_flags,
            created_at
        FROM raw_xbrl_facts
        WHERE id = ?
        """,
        [legacy_id],
    )
    duplicate_id = duplicate_cursor.lastrowid
    company_cursor = connection.execute(
        """
        INSERT INTO companies (cik, name, created_at, updated_at)
        VALUES ('0000320193', 'Apple Inc.', '2025-01-31', '2025-01-31')
        """
    )
    company_id = company_cursor.lastrowid
    connection.executemany(
        """
        INSERT INTO financial_metrics (
            company_id,
            accession_number,
            raw_fact_id,
            statement_type,
            metric_name,
            value_numeric,
            value_raw,
            unit,
            period_type,
            fiscal_year,
            fiscal_period,
            start_date,
            end_date,
            filing_date,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                company_id,
                "0000320193-25-000001",
                raw_fact_id,
                "income_statement",
                "revenue",
                "100",
                "100",
                "USD",
                "annual",
                2024,
                "FY",
                "2024-01-01",
                "2024-12-31",
                "2025-01-31",
                "2025-01-31",
            )
            for raw_fact_id in (legacy_id, duplicate_id)
        ],
    )
    metric_id_by_raw_fact_id = {
        row["raw_fact_id"]: row["metric_id"]
        for row in connection.execute(
            "SELECT metric_id, raw_fact_id FROM financial_metrics"
        ).fetchall()
    }
    connection.execute(
        """
        INSERT INTO financial_indicators (
            company_id,
            indicator_name,
            formula_name,
            formula_version,
            unit,
            period_type,
            source_metric_ids,
            source_raw_fact_ids,
            source_accession_numbers,
            calculation_status,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            company_id,
            "revenue_growth",
            "growth",
            "1",
            "percent",
            "annual",
            json.dumps([metric_id_by_raw_fact_id[duplicate_id]]),
            json.dumps([duplicate_id]),
            json.dumps(["0000320193-25-000001"]),
            "calculated",
            "2025-01-31",
        ],
    )
    connection.commit()

    repository.initialize()
    migrated_records = repository.list_fact_records("0000320193")

    assert len(migrated_records) == 1
    assert migrated_records[0].occurrence_count == 2
    metric_rows = connection.execute(
        "SELECT metric_id, raw_fact_id FROM financial_metrics"
    ).fetchall()
    assert [row["raw_fact_id"] for row in metric_rows] == [legacy_id]
    indicator_row = connection.execute(
        """
        SELECT source_metric_ids, source_raw_fact_ids
        FROM financial_indicators
        """
    ).fetchone()
    assert json.loads(indicator_row["source_metric_ids"]) == [
        metric_rows[0]["metric_id"]
    ]
    assert json.loads(indicator_row["source_raw_fact_ids"]) == [legacy_id]

    updated_provenance = replace(
        _normalized_facts()[0],
        value_raw=100,
        value=Decimal("100"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        period_type="annual",
        fiscal_year=2025,
        fiscal_period="Q4",
        form="10-K/A",
        filed_date=date(2025, 2, 14),
        accession_number="0000320193-25-000001",
        frame="CY2024Q4",
        context_id="context-b",
        source_document="filing-b.htm",
    )
    repository.upsert_facts([updated_provenance])
    record = repository.list_fact_records("0000320193")[0]

    assert record.raw_fact_id == legacy_id
    assert record.occurrence_count == 2
    assert len(record.occurrence_references) == 2


def test_raw_fact_repository_round_trips_quality_flags(tmp_path: Path) -> None:
    connection = connect_sqlite(tmp_path / "stock.db")
    repository = RawFactRepository(connection)
    repository.initialize()
    duplicate_fact = next(
        fact for fact in _normalized_facts() if fact.concept == "Revenues" and DUPLICATE_FACT in fact.quality_flags
    )

    repository.upsert_facts([duplicate_fact])
    stored = repository.list_facts("0000320193")

    assert stored[0].quality_flags == (DUPLICATE_FACT,)
