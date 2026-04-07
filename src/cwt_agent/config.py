"""Load settings from environment (.env via python-dotenv)."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[2]


# Exported for CLI (doctor / paths)
_ROOT = _resolve_project_root()


def _load_dotenv_files() -> None:
    load_dotenv(_ROOT / ".env", override=True, encoding="utf-8-sig")
    cwd_env = Path.cwd() / ".env"
    if cwd_env.resolve() != (_ROOT / ".env").resolve():
        load_dotenv(cwd_env, override=True, encoding="utf-8-sig")

    or_k = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if or_k:
        os.environ["OPENAI_API_KEY"] = or_k


_load_dotenv_files()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
        env_ignore_empty=True,
    )

    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_chat_model: str = Field(
        default="qwen/qwen3.6-plus:free",
        validation_alias="OPENROUTER_CHAT_MODEL",
    )
    openrouter_embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2:free",
        validation_alias="OPENROUTER_EMBEDDING_MODEL",
    )
    openrouter_embedding_fallback_model: str = Field(
        default="",
        validation_alias="OPENROUTER_EMBEDDING_FALLBACK_MODEL",
    )
    openrouter_http_referer: str = Field(
        default="https://openrouter.ai/",
        validation_alias="OPENROUTER_HTTP_REFERER",
    )
    openrouter_app_title: str = Field(
        default="CWT Prediction Agent",
        validation_alias="OPENROUTER_APP_TITLE",
    )

    apify_token: str = Field(default="", validation_alias="APIFY_TOKEN")
    apify_polymarket_actor: str = Field(
        default="fatihtahta/polymarket-scraper-mo",
        validation_alias="APIFY_POLYMARKET_ACTOR",
    )

    kalshi_api_key_id: str = Field(default="", validation_alias="KALSHI_API_KEY_ID")
    kalshi_private_key_path: str = Field(
        default="",
        validation_alias="KALSHI_PRIVATE_KEY_PATH",
    )

    cwt_data_dir: Path = Field(default=Path("./data"), validation_alias="CWT_DATA_DIR")
    chroma_collection: str = Field(default="cwt_events", validation_alias="CHROMA_COLLECTION")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator(
        "openrouter_api_key",
        "apify_token",
        "kalshi_api_key_id",
        "kalshi_private_key_path",
        "openrouter_embedding_fallback_model",
        mode="before",
    )
    @classmethod
    def strip_secrets(cls, v: object) -> str:
        if v is None:
            return ""
        s = str(v).strip().lstrip("\ufeff")
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            s = s[1:-1].strip()
        return s

    @model_validator(mode="after")
    def pull_secrets_from_os_environ(self) -> Self:
        if not self.openrouter_api_key:
            object.__setattr__(
                self,
                "openrouter_api_key",
                os.environ.get("OPENROUTER_API_KEY", "").strip().lstrip("\ufeff"),
            )
        if not self.apify_token:
            object.__setattr__(
                self,
                "apify_token",
                os.environ.get("APIFY_TOKEN", "").strip().lstrip("\ufeff"),
            )
        return self

    @property
    def chroma_path(self) -> Path:
        p = self.cwt_data_dir.resolve() / "chroma"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def digest_path(self) -> Path:
        p = self.cwt_data_dir.resolve() / "traders_digest.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    _load_dotenv_files()
    return get_settings()