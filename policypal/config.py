"""Application settings, read from environment variables (and a local .env file).

Every setting is documented in .env.example. Invalid or missing values stop the app at
startup with a clear validation error instead of failing later.
"""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ORIGIN = re.compile(r"^https?://[^/\s]+$")

# The ADMIN_TOKEN in .env.example. It is public, so the API warns at start-up while it is
# still in use.
PLACEHOLDER_ADMIN_TOKEN = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: there is no safe default for where the data lives.
    database_url: str
    # "fake" is deliberately not allowed: the fake LLM exists only in the test suite.
    llm_provider: Literal["ollama", "extractive"] = "ollama"
    # Inside Docker Compose this is http://ollama:11434 (set in docker-compose.yml).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    # After this many seconds the app stops waiting and quotes the policies instead. 120
    # leaves room for a cold start: the first answer after the model loads took 33-58 s
    # on a CPU laptop (warm answers about 24 s).
    ollama_timeout_seconds: float = Field(default=120, gt=0, le=600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Local sentence-transformers model. Changing it needs an image rebuild (the model is
    # downloaded at build time) and must keep 384-number vectors (see migration 0002).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Added to the front of every question (never to policy passages), as the bge model
    # card recommends for short-question-to-passage search. Set to "" to turn it off.
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages: "
    # How many of the most similar chunks a search returns.
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    # Refuse when the best chunk's cosine similarity is below this. It is a score, not a
    # probability. 0.69 was chosen on the evaluation's dev set by the best balanced accuracy,
    # with the query instruction on: first on 20 questions (v1), then again on 40 (v2):
    # evaluation/results/v2/dev-calibration.md. With the instruction off it is 0.71.
    min_similarity: float = Field(default=0.69, ge=0, le=1)

    # Shared demo token for the admin endpoints (upload, re-ingest), sent in the
    # X-Admin-Token header. Unset or empty: admin endpoints are switched off.
    admin_token: SecretStr | None = None
    max_upload_mb: int = Field(default=5, ge=1, le=50)
    # Uploaded policies are saved here (a Docker volume in Compose) and re-ingested on start.
    upload_dir: Path = Path("uploads")

    # Other websites whose pages may call the API from the browser (an embedded widget), as
    # a comma-separated list such as "http://localhost:8080,https://intranet.example.com".
    # Empty (the default): only pages served by the API itself, such as /widget/demo.html.
    # NoDecode: read the plain text here instead of expecting a JSON list.
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _scheme_and_host_only(cls, origins: list[str]) -> list[str]:
        # A browser sends its origin as scheme://host[:port], with no path or slash.
        for origin in origins:
            if not _ORIGIN.match(origin):
                raise ValueError(f"{origin!r} is not an origin like http://localhost:8080")
        return origins

    @field_validator("admin_token", mode="before")
    @classmethod
    def _empty_token_means_off(cls, value: object) -> object:
        return None if value == "" else value
