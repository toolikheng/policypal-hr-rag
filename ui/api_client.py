"""The only place the Streamlit UI talks to the PolicyPal API (over HTTP).

Each method returns the API's JSON as a typed dictionary, or raises ApiError with a
message that is safe to show on the page.
"""

import os
from typing import Any, Literal, Protocol, TypedDict

import httpx

# The API may wait up to OLLAMA_TIMEOUT_SECONDS (default 120) for the LLM before it falls
# back to quoting the policies, and re-ingesting can embed every policy. Wait longer.
SLOW_TIMEOUT_SECONDS = 180


class ApiError(Exception):
    """The API could not be reached, or refused the request. str() is the message to show."""

    def __init__(
        self, message: str, status_code: int | None = None, conflict: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        # For an upload 409: "name_taken" (can be replaced) or "sample_policy" (can't).
        self.conflict = conflict


class Health(TypedDict):
    status: str
    database: str
    version: str


class Citation(TypedDict):
    number: int
    document_id: int
    document_title: str
    section: str
    text: str
    similarity: float


class Answer(TypedDict):
    message_id: str
    conversation_id: str
    answer: str
    mode: Literal["llm", "extractive", "refused"]
    refused: bool
    citations: list[Citation]
    model: str | None
    fallback_reason: str | None
    latency_ms: dict[str, int | None]


class Document(TypedDict):
    id: int
    slug: str
    title: str
    file_type: str
    origin: str
    chunks: int
    updated_at: str


class ChunkText(TypedDict):
    id: int
    text: str


class Section(TypedDict):
    section: str
    section_path: str
    chunks: list[ChunkText]


class DocumentDetail(Document):
    sections: list[Section]


class UploadResult(TypedDict):
    status: Literal["created", "updated", "unchanged"]
    document: Document


class IngestResult(TypedDict):
    slug: str
    status: str
    chunks: int


class QuestionCount(TypedDict):
    question: str
    count: int
    last_asked: str


class FallbackCount(TypedDict):
    reason: str
    count: int


class Analytics(TypedDict):
    period_days: int
    total_questions: int
    answered: int
    refused: int
    refusal_rate: float | None
    feedback: dict[str, Any]  # count, up, down, feedback_rate, helpful_rate
    avg_latency_ms: dict[str, int | None]  # overall, llm, extractive
    top_questions: list[QuestionCount]
    unanswered_questions: list[QuestionCount]
    fallbacks: list[FallbackCount]


class PolicyPalApi(Protocol):
    """Everything the pages may ask of the API. PolicyPalClient does it over HTTP; page
    tests use a fake (tests/fakes.py). A test checks that both match this interface."""

    def health(self) -> Health: ...

    def ask(self, question: str, conversation_id: str | None = None) -> Answer: ...

    def feedback(self, message_id: str, rating: str, comment: str | None = None) -> None: ...

    def list_documents(self) -> list[Document]: ...

    def get_document(self, document_id: int) -> DocumentDetail: ...

    def upload(
        self, filename: str, data: bytes, *, token: str, replace: bool = False
    ) -> UploadResult: ...

    def reingest(self, *, token: str) -> list[IngestResult]: ...

    def analytics(self, days: int, *, token: str) -> Analytics: ...


def make_client() -> "PolicyPalClient":
    """A client for the API at API_URL (the pages call this; tests replace it)."""
    base_url = os.environ.get("API_URL", "http://localhost:8000")
    return PolicyPalClient(httpx.Client(base_url=base_url, timeout=10))


class PolicyPalClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    @property
    def base_url(self) -> httpx.URL:
        return self._http.base_url

    def health(self) -> Health:
        """The API's /health report. 503 is a normal answer: the API is up but not ready."""
        return self._send("GET", "/health", ok=(200, 503))

    def ask(self, question: str, conversation_id: str | None = None) -> Answer:
        body = {"question": question, "conversation_id": conversation_id, "channel": "ui"}
        return self._send("POST", "/ask", json=body, timeout=SLOW_TIMEOUT_SECONDS)

    def feedback(self, message_id: str, rating: str, comment: str | None = None) -> None:
        body = {"message_id": message_id, "rating": rating, "comment": comment}
        self._send("POST", "/feedback", json=body)

    def list_documents(self) -> list[Document]:
        return self._send("GET", "/documents")

    def get_document(self, document_id: int) -> DocumentDetail:
        return self._send("GET", f"/documents/{document_id}")

    def upload(
        self, filename: str, data: bytes, *, token: str, replace: bool = False
    ) -> UploadResult:
        return self._send(
            "POST",
            "/documents",
            ok=(200, 201),
            files={"file": (filename, data)},
            params={"replace": "true" if replace else "false"},
            headers={"X-Admin-Token": token},
            timeout=SLOW_TIMEOUT_SECONDS,
        )

    def reingest(self, *, token: str) -> list[IngestResult]:
        reply = self._send(
            "POST",
            "/documents/reingest",
            headers={"X-Admin-Token": token},
            timeout=SLOW_TIMEOUT_SECONDS,
        )
        return reply["results"]

    def analytics(self, days: int, *, token: str) -> Analytics:
        return self._send(
            "GET", "/analytics", params={"days": days}, headers={"X-Admin-Token": token}
        )

    def _send(self, method: str, path: str, ok: tuple[int, ...] = (200,), **kwargs: Any) -> Any:
        """Make one request; return its JSON, or raise ApiError with a readable message."""
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiError("The PolicyPal API took too long to answer. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Cannot reach the PolicyPal API at {self._http.base_url}.") from exc
        try:
            body = response.json()
        except ValueError:
            body = None  # e.g. a proxy's HTML error page
        if response.status_code not in ok:
            raise ApiError(
                _message(body, response.status_code),
                status_code=response.status_code,
                conflict=body.get("conflict") if isinstance(body, dict) else None,
            )
        if body is None:
            raise ApiError("The PolicyPal API reply was not valid JSON.")
        return body


def _message(body: Any, status_code: int) -> str:
    """The API's `detail` (a string, or a list of problems for invalid input).

    For a server error, the status and request ID instead, so a user can report it.
    """
    if status_code >= 500:
        request_id = body.get("request_id") if isinstance(body, dict) else None
        reference = f", reference {request_id}" if request_id else ""
        return f"The PolicyPal API had a problem (HTTP {status_code}{reference})."
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        problems = [
            f"{problem.get('loc', ['?'])[-1]}: {problem.get('msg', 'invalid')}"
            for problem in detail
            if isinstance(problem, dict)
        ]
        if problems:
            return "; ".join(problems)
    return f"Unexpected reply from the PolicyPal API (HTTP {status_code})."
