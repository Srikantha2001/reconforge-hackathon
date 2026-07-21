"""Centralized configuration for ReconForge.

Every tunable lives here and is sourced from the environment (.env). Nothing
else in the codebase should read os.environ directly.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Resolve .env from the repo root regardless of the working directory.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---------------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./data/reconforge.db"

    # --- LLM provider -----------------------------------------------------
    llm_provider: str = "stub"  # stub | gemini | openai
    llm_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None

    # --- App --------------------------------------------------------------
    stp_threshold: float = 0.90
    upload_dir: str = "./uploads"
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
