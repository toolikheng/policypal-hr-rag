"""The only place the Streamlit UI talks to the PolicyPal API (over HTTP)."""

from typing import TypedDict

import httpx


class ApiError(Exception):
    """The API could not be reached, or sent a reply the UI doesn't understand."""


class Health(TypedDict):
    status: str
    database: str
    version: str


class PolicyPalClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def health(self) -> Health:
        """Return the API's /health report. 503 is a normal answer: the API is up but not ready."""
        try:
            response = self._http.get("/health")
        except httpx.HTTPError as exc:
            raise ApiError(f"Cannot reach the PolicyPal API at {self._http.base_url}.") from exc
        if response.status_code not in (200, 503):
            raise ApiError(
                f"Unexpected reply from the PolicyPal API (HTTP {response.status_code})."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("The PolicyPal API reply was not valid JSON.") from exc
