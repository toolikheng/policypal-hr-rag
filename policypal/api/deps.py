"""Typed access to what the app builds at startup, for use in endpoints via Depends().

create_app() stores these on `app.state`; tests swap in fakes by passing them to
create_app(). Endpoints declare what they need, e.g. `def ask(engine: EngineDep)`.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
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


# Documented in Swagger as an API key (the "Authorize" button). auto_error=False lets
# require_admin() choose the status code and message.
admin_token_header = APIKeyHeader(
    name="X-Admin-Token",
    description="The admin token (ADMIN_TOKEN in .env).",
    auto_error=False,
)


def require_admin(
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Security(admin_token_header)],
) -> None:
    """Allow the request only with the right X-Admin-Token header.

    A shared demo token, not real user authentication (there are no user accounts).
    """
    if settings.admin_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Admin features are disabled: set ADMIN_TOKEN."
        )
    if not x_admin_token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Admin token required in the X-Admin-Token header."
        )
    # compare_digest takes the same time whether the first or the last character differs,
    # so response times don't leak how much of a guess was right.
    expected = settings.admin_token.get_secret_value().encode()
    if not secrets.compare_digest(x_admin_token.encode(), expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin token is not valid.")
