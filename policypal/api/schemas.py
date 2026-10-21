"""Request and response models. The examples appear in Swagger at /docs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from policypal.db import DatabaseStatus


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: DatabaseStatus
    version: str

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"status": "ok", "database": "ok", "version": "0.1.0"}]}
    )
