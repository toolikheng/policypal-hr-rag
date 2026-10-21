"""The only place the Streamlit UI talks to the PolicyPal API (over HTTP)."""

import httpx


class ApiUnavailableError(Exception):
    """The API could not be reached at all (as opposed to returning an error)."""


class PolicyPalClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def health(self) -> dict:
        """Return the API's /health body. A 503 still has a body describing the problem."""
        try:
            response = self._http.get("/health")
        except httpx.HTTPError as exc:
            raise ApiUnavailableError(
                f"Cannot reach the PolicyPal API at {self._http.base_url}"
            ) from exc
        return response.json()
