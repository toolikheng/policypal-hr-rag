"""Application settings, read from environment variables (and a local .env file).

Every setting has a documented default in .env.example. Invalid values stop the app at
startup with a clear validation error instead of failing later.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://policypal:policypal-local-dev@localhost:5433/policypal"
    )
    # "fake" is deliberately not allowed: the fake LLM exists only in the test suite.
    llm_provider: Literal["ollama", "extractive"] = "ollama"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
