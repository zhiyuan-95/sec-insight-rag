import json
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

    assert inserted == len(facts)
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
