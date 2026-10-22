"""Application settings, read from environment variables (and a local .env file).

Every setting is documented in .env.example. Invalid or missing values stop the app at
startup with a clear validation error instead of failing later.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: there is no safe default for where the data lives.
    database_url: str
    # "fake" is deliberately not allowed: the fake LLM exists only in the test suite.
    llm_provider: Literal["ollama", "extractive"] = "ollama"
    # Inside Docker Compose this is http://ollama:11434 (set in docker-compose.yml).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    # A CPU can take tens of seconds per answer; after this the app quotes the policies.
    ollama_timeout_seconds: float = Field(default=60, gt=0, le=600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Local sentence-transformers model. Changing it needs an image rebuild (the model is
    # downloaded at build time) and must keep 384-number vectors (see migration 0002).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Added to the front of every question (never to policy passages), as the bge model
    # card recommends for short-question-to-passage search. Set to "" to turn it off.
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages: "
    # How many of the most similar chunks a search returns.
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
