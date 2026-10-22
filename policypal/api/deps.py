"""Typed access to what the app builds at startup, for use in endpoints via Depends().

create_app() stores these on `app.state`; tests swap in fakes by passing them to
create_app(). Endpoints declare what they need, e.g. `def ask(engine: EngineDep)`.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine

from policypal.config import Settings
from policypal.embeddings import Embedder
from policypal.llm.base import LLMProvider


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_embedder(request: Request) -> Embedder:
    return request.app.state.embedder


def get_llm(request: Request) -> LLMProvider | None:
    """None means no LLM is configured (LLM_PROVIDER=extractive)."""
    return request.app.state.llm


SettingsDep = Annotated[Settings, Depends(get_settings)]
EngineDep = Annotated[Engine, Depends(get_engine)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
LLMDep = Annotated[LLMProvider | None, Depends(get_llm)]
