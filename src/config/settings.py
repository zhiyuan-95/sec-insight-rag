"""Runtime settings loaded from local environment files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CHAT_MODEL = "gemini-2.5-flash"
SUPPORTED_CHAT_MODELS = {DEFAULT_CHAT_MODEL}


class Settings(BaseSettings):
    """Application settings for local development and runtime configuration."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("Gemini_API_KEY", "GEMINI_API_KEY"),
    )
    sec_user_agent: str | None = Field(
        default=None,
        validation_alias="SEC_USER_AGENT",
    )
    stock_sql_db_path: Path = Field(
        default=Path("stock_data.db"),
        validation_alias="STOCK_SQL_DB_PATH",
    )
    stock_storage_base_dir: Path = Field(
        default=Path("./storage/stock"),
        validation_alias="STOCK_STORAGE_BASE_DIR",
    )
    stock_filings_base_dir: Path = Field(
        default=Path("./data_store/filings"),
        validation_alias="STOCK_FILINGS_BASE_DIR",
    )
    knowledge_storage_dir: Path | None = Field(
        default=None,
        validation_alias="KNOWLEDGE_STORAGE_DIR",
    )
    primary_chat_model: str = Field(
        default=DEFAULT_CHAT_MODEL,
        validation_alias="PRIMARY_CHAT_MODEL",
    )
    allowed_chat_models: list[str] = Field(
        default_factory=lambda: [DEFAULT_CHAT_MODEL],
        validation_alias="ALLOWED_CHAT_MODELS",
    )

    @field_validator("allowed_chat_models", mode="before")
    @classmethod
    def parse_allowed_chat_models(cls, value: Any) -> list[str]:
        """Accept JSON or comma-separated model lists from env files."""
        if value is None:
            return [DEFAULT_CHAT_MODEL]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return [DEFAULT_CHAT_MODEL]
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("ALLOWED_CHAT_MODELS must be a list")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        raise TypeError("ALLOWED_CHAT_MODELS must be a list or string")

    @model_validator(mode="after")
    def validate_chat_models(self) -> Settings:
        """Keep Milestone 1 model configuration pinned to Gemini Flash."""
        configured = {self.primary_chat_model, *self.allowed_chat_models}
        unsupported = configured - SUPPORTED_CHAT_MODELS
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"Unsupported chat model configured: {names}")
        if self.primary_chat_model not in self.allowed_chat_models:
            raise ValueError("PRIMARY_CHAT_MODEL must be in ALLOWED_CHAT_MODELS")
        return self


def load_settings(env_file: str | Path = "config.env") -> Settings:
    """Load settings from a local env file without printing secret values."""
    values = _read_env_file(Path(env_file))
    return Settings.model_validate(values)


def _read_env_file(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_optional_quotes(value.strip())
        if key:
            values[key] = value
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
