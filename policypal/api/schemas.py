"""Request and response models. The examples appear in Swagger at /docs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

from policypal.db import DatabaseStatus


class HealthResponse(BaseModel):
    database: DatabaseStatus
    version: str

    @computed_field
    @property
    def status(self) -> Literal["ok", "unavailable"]:
        """Overall status, derived from the checks so it can never disagree with them."""
        return "ok" if self.database == "ok" else "unavailable"

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"status": "ok", "database": "ok", "version": "0.1.0"}]}
    )
