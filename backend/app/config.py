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

    # --- Auth (P4 consumes; declared in P2 so all config lives in one place) --
    secret_key: str = "reconos-hackathon-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_hours: int = 24

    # --- Governance thresholds (P5) ---------------------------------------
    write_off_auto_approve_below: float = 500.00
    write_off_dual_checker_above: float = 10000.00
    pending_approval_expiry_hours: int = 24

    # --- Regulatory thresholds (P6) ---------------------------------------
    emir_amount_threshold_eur: float = 15000000.00
    emir_days_threshold: int = 15
    cass_shortfall_threshold_eur: float = 1000.00

    # --- Subset-sum performance guards (P3) --------------------------------
    subset_sum_max_group_size: int = 4
    subset_sum_max_rows_per_partition: int = 50
    subset_sum_timeout_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
