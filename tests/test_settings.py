from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_INDUSTRY_CLASSIFICATION_MODEL,
    load_settings,
)


def test_load_settings_trims_env_keys_and_values(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        "\n".join(
            [
                "Gemini_API_KEY = super-secret",
                " SEC_USER_AGENT = Example Agent contact@example.com ",
                "STOCK_SQL_DB_PATH = stock_data.db",
                "STOCK_STORAGE_BASE_DIR = ./storage/stock",
                "STOCK_FILINGS_BASE_DIR = ./data_store/filings",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "super-secret"
    assert str(settings.gemini_api_key) == "**********"
    assert settings.sec_user_agent == "Example Agent contact@example.com"
    assert settings.stock_sql_db_path == Path("stock_data.db")
    assert settings.stock_storage_base_dir == Path("./storage/stock")
    assert settings.stock_filings_base_dir == Path("./data_store/filings")
    assert settings.knowledge_storage_dir == Path("data_store/knowledge")


def test_load_settings_defaults_missing_optional_values(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text("SEC_USER_AGENT=Example Agent contact@example.com\n", encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.knowledge_storage_dir == Path("data_store/knowledge")
    assert settings.primary_chat_model == DEFAULT_CHAT_MODEL
    assert settings.allowed_chat_models == [DEFAULT_CHAT_MODEL]
    assert settings.openai_formula_proposal_model == "gpt-5-mini"
    assert settings.gemini_flash_lite_formula_proposal_model == "gemini-3.1-flash-lite"
    assert settings.gemini_formula_proposal_model == "gemini-2.5-flash"
    assert (
        settings.industry_classification_model
        == DEFAULT_INDUSTRY_CLASSIFICATION_MODEL
    )


def test_load_settings_accepts_formula_model_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_FORMULA_PROPOSAL_MODEL=openai-override",
                "GEMINI_FLASH_LITE_FORMULA_PROPOSAL_MODEL=flash-lite-override",
                "GEMINI_FORMULA_PROPOSAL_MODEL=gemini-override",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.openai_formula_proposal_model == "openai-override"
    assert settings.gemini_flash_lite_formula_proposal_model == "flash-lite-override"
    assert settings.gemini_formula_proposal_model == "gemini-override"


def test_load_settings_accepts_industry_classification_model_override(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        "INDUSTRY_CLASSIFICATION_MODEL=industry-override\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.industry_classification_model == "industry-override"


def test_load_settings_rejects_empty_industry_classification_model(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        "INDUSTRY_CLASSIFICATION_MODEL=' '\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_settings(env_file)


def test_load_settings_accepts_comma_separated_allowed_models(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text(
        f"ALLOWED_CHAT_MODELS={DEFAULT_CHAT_MODEL}\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.allowed_chat_models == [DEFAULT_CHAT_MODEL]


def test_load_settings_rejects_unsupported_chat_model(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text("PRIMARY_CHAT_MODEL=other-model\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_settings(env_file)
