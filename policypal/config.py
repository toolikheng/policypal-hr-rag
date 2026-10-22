"""Application settings, read from environment variables (and a local .env file).

Every setting is documented in .env.example. Invalid or missing values stop the app at
startup with a clear validation error instead of failing later.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: there is no safe default for where the data lives.
    database_url: str
    # "fake" is deliberately not allowed: the fake LLM exists only in the test suite.
    llm_provider: Literal["ollama", "extractive"] = "ollama"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Local sentence-transformers model. Changing it needs an image rebuild (the model is
    # downloaded at build time) and must keep 384-number vectors (see migration 0002).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
