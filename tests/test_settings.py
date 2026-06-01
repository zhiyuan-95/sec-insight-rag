from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.settings import DEFAULT_CHAT_MODEL, load_settings


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
    assert settings.knowledge_storage_dir is None


def test_load_settings_defaults_missing_optional_values(tmp_path: Path) -> None:
    env_file = tmp_path / "config.env"
    env_file.write_text("SEC_USER_AGENT=Example Agent contact@example.com\n", encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.knowledge_storage_dir is None
    assert settings.primary_chat_model == DEFAULT_CHAT_MODEL
    assert settings.allowed_chat_models == [DEFAULT_CHAT_MODEL]


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
