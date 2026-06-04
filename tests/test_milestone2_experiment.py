import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType


def _load_experiment_module() -> ModuleType:
    module_path = Path("experiments/MS2/milestone2_ingestion_showcase.py")
    spec = importlib.util.spec_from_file_location("milestone2_ingestion_showcase", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_milestone2_fixture_mode_prints_showcase(tmp_path: Path, capsys) -> None:
    experiment = _load_experiment_module()

    exit_code = experiment.main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "fixture",
            "--db-path",
            str(tmp_path / "fixture.db"),
            "--filings-dir",
            str(tmp_path / "filings"),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Milestone 2 Experiment: SEC/XBRL Ingestion And Normalization" in output
    assert "mode: fixture" in output
    assert "Company Resolution:" in output
    assert "Filing Period Coverage:" in output
    assert "Downloaded Filing Paths:" in output
    assert "XBRL Normalization:" in output
    assert "XBRL Concepts Stored In Database:" in output
    assert "concept filter: common us-gaap concept list" in output
    assert "concepts stored:" not in output
    assert "normalized fact count: 5" in output
    assert "stored row count: 4" in output
    assert "distinct concepts ingested: 2" in output
    assert "taxonomy" in output
    assert "stored rows" in output
    assert "Income statement:" in output
    assert "Balance sheet:" in output
    assert "Assets" in output
    assert "Revenues" in output
    assert "database table: raw_xbrl_facts" in output
    assert "Top 5 raw_xbrl_facts Rows:" in output
    assert "ambiguous_unit" in output
    assert "duplicate_fact" in output
    assert "Result:" not in output


def test_milestone2_fixture_mode_rejects_unsupported_ticker(capsys) -> None:
    experiment = _load_experiment_module()

    exit_code = experiment.main(["--ticker", "MSFT", "--mode", "fixture"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Unsupported Fixture Ticker:" in output
    assert "supports only AAPL" in output
    assert "no live SEC call was made" in output
    assert "Result:" not in output


def test_milestone2_live_mode_rejects_missing_sec_user_agent(tmp_path: Path, capsys) -> None:
    experiment = _load_experiment_module()
    env_file = tmp_path / "config.env"
    env_file.write_text(
        "\n".join(
            [
                f"STOCK_SQL_DB_PATH={tmp_path / 'stock.db'}",
                f"STOCK_FILINGS_BASE_DIR={tmp_path / 'filings'}",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = experiment.main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "live",
            "--env-file",
            str(env_file),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "SEC_USER_AGENT is required for SEC ingestion" in output
    assert "Execution Error:" in output
    assert "Result:" not in output


def test_milestone2_report_uses_selected_filing_scope_for_human_sections() -> None:
    experiment = _load_experiment_module()
    annual_filing = experiment.FilingMetadata(
        cik="0001318605",
        accession_number="0001628280-26-003952",
        form="10-K",
        filing_date="2026-01-29",
        primary_document="tsla-20251231.htm",
        document_url="https://example.test/10k",
    )
    quarterly_filing = experiment.FilingMetadata(
        cik="0001318605",
        accession_number="0001628280-26-026673",
        form="10-Q",
        filing_date="2026-04-23",
        primary_document="tsla-20260331.htm",
        document_url="https://example.test/10q",
    )
    result = experiment.ExperimentResult(
        mode="live",
        ticker="TSLA",
        cik="0001318605",
        company_name="Tesla, Inc.",
        database_path=Path("stock_data.db"),
        filings_directory=Path("data_store/filings"),
        filings=(annual_filing, quarterly_filing),
        downloaded_paths=(Path("10k.htm"), Path("10q.htm")),
        normalized_facts=(
            _fact(experiment, fiscal_year=2011, fiscal_period="FY", form="10-K", accession_number="old-10k"),
            _fact(experiment, fiscal_year=2025, fiscal_period="FY", form="10-K", accession_number="0001628280-26-003952"),
            _fact(experiment, fiscal_year=2026, fiscal_period="Q1", form="10-Q", accession_number="0001628280-26-026673"),
        ),
        stored_records=(
            experiment.StoredRawFact(
                raw_fact_id=1,
                fact=_fact(experiment, fiscal_year=2011, fiscal_period="FY", form="10-K", accession_number="old-10k"),
            ),
            experiment.StoredRawFact(
                raw_fact_id=2,
                fact=_fact(experiment, fiscal_year=2025, fiscal_period="FY", form="10-K", accession_number="0001628280-26-003952"),
            ),
            experiment.StoredRawFact(
                raw_fact_id=3,
                fact=_fact(experiment, fiscal_year=2026, fiscal_period="Q1", form="10-Q", accession_number="0001628280-26-026673"),
            ),
        ),
        upsert_attempt_count=3,
    )

    output = experiment.format_report(result)

    assert "10-K  1 fiscal year" in output
    assert "10-Q  1 fiscal quarter" in output
    assert "FY2025" in output
    assert "FY2026 Q1" in output
    assert "FY2011" not in output


def test_milestone2_concepts_are_grouped_by_statement_section() -> None:
    experiment = _load_experiment_module()
    result = experiment.ExperimentResult(
        mode="fixture",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        database_path=Path("fixture.db"),
        filings_directory=Path("filings"),
        filings=(),
        downloaded_paths=(),
        normalized_facts=(),
        stored_records=(
            experiment.StoredRawFact(raw_fact_id=1, fact=_fact(experiment, concept="Revenues")),
            experiment.StoredRawFact(raw_fact_id=2, fact=_fact(experiment, concept="Assets")),
            experiment.StoredRawFact(
                raw_fact_id=3,
                fact=_fact(experiment, concept="NetCashProvidedByUsedInOperatingActivities"),
            ),
            experiment.StoredRawFact(raw_fact_id=4, fact=_fact(experiment, concept="EarningsPerShareBasic")),
            experiment.StoredRawFact(
                raw_fact_id=5,
                fact=_fact(experiment, concept="OtherComprehensiveIncomeLossNetOfTax"),
            ),
            experiment.StoredRawFact(raw_fact_id=6, fact=_fact(experiment, concept="CustomFact")),
        ),
        upsert_attempt_count=6,
    )

    output = experiment.format_report(result)

    assert "Income statement:" in output
    assert "Balance sheet:" in output
    assert "Cash flow statement:" in output
    assert "EPS and shares:" in output
    assert "Other comprehensive income:" in output
    assert "Unmapped financial facts:" in output
    concept_section = output.split("XBRL Concepts Stored In Database:", maxsplit=1)[1]
    concept_section = concept_section.split("Top 5 raw_xbrl_facts Rows:", maxsplit=1)[0]
    assert concept_section.index("Income statement:") < concept_section.index("Revenues")
    assert concept_section.index("Balance sheet:") < concept_section.index("Assets")
    assert concept_section.index("Unmapped financial facts:") < concept_section.index("CustomFact")


def _fact(
    experiment: ModuleType,
    *,
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    form: str = "10-K",
    accession_number: str = "0000320193-25-000079",
    concept: str = "Assets",
):
    return experiment.NormalizedFact(
        cik="0001318605",
        entity_name="Tesla, Inc.",
        taxonomy="us-gaap",
        concept=concept,
        label=concept,
        description=None,
        unit="USD",
        value_raw=100,
        value=Decimal("100"),
        start_date=date(fiscal_year, 1, 1),
        end_date=date(fiscal_year, 12, 31),
        period_type="duration",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed_date=date(fiscal_year, 12, 31),
        accession_number=accession_number,
        frame=None,
        source="sec_companyfacts",
    )
