"""Ollama: a local LLM server, called over its HTTP API (no SDK needed for two endpoints)."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import httpx

from policypal.llm.base import LLMError, LLMStatus
from policypal.llm.prompt import build_messages
from policypal.retrieval import RetrievedChunk

# /health runs often and must stay fast even when Ollama is down or hangs.
STATUS_TIMEOUT_SECONDS = 1  # for each HTTP step (connect, read)
# For the whole check. It also covers the DNS lookup, which no HTTP timeout interrupts: with
# the ollama container gone, the lookup alone took 3.3 s, longer than Docker's healthcheck.
STATUS_DEADLINE_SECONDS = 1.0
# Status checks run here so /health can stop waiting. A check stuck on DNS keeps its thread
# until the lookup fails; four threads are plenty for one health check every few seconds.
_status_checks = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ollama-status")
# Keep the model in memory between questions: loading it again takes seconds on CPU.
KEEP_ALIVE = "30m"
GENERATION_OPTIONS = {
    "temperature": 0,  # the most likely words every time: repeatable answers
    "num_predict": 300,  # at most ~300 tokens in the answer
    "num_ctx": 4096,  # room for the rules, five excerpts and the question
}


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,  # tests pass a fake HTTP layer
    ) -> None:
        self.model = model
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def generate(self, question: str, excerpts: Sequence[RetrievedChunk]) -> str:
        payload = {
            "model": self.model,
            "messages": build_messages(question, excerpts),
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": GENERATION_OPTIONS,
        }
        try:
            with self._client(self._timeout_seconds) as client:
                response = client.post("/api/chat", json=payload)
        # TimeoutException is a kind of TransportError, so it must be caught first.
        except httpx.TimeoutException as exc:
            raise LLMError(
                "llm_timeout", f"Ollama did not answer within {self._timeout_seconds:g} s."
            ) from exc
        except httpx.TransportError as exc:
            raise LLMError("llm_unavailable", "Ollama could not be reached.") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            raise LLMError("llm_model_missing", f"Ollama has no model named '{self.model}'.")
        if response.is_error:
            raise LLMError("llm_error", f"Ollama returned HTTP {response.status_code}.")
        try:
            reply = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("llm_bad_response", "Ollama's reply had no message.") from exc
        if not isinstance(reply, str):
            raise LLMError("llm_bad_response", "Ollama's reply was not text.")
        return reply

    def status(self) -> LLMStatus:
        """ok, model_missing, or unavailable, within STATUS_DEADLINE_SECONDS."""
        check = _status_checks.submit(self._check_status)
        try:
            return check.result(timeout=STATUS_DEADLINE_SECONDS)
        except TimeoutError:
            return "unavailable"

    def _check_status(self) -> LLMStatus:
        try:
            with self._client(STATUS_TIMEOUT_SECONDS) as client:
                response = client.get("/api/tags")
            response.raise_for_status()
            downloaded = {model["name"] for model in response.json()["models"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return "unavailable"
        # Ollama lists "llama3.2" as "llama3.2:latest".
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        return "ok" if wanted in downloaded else "model_missing"

    def _client(self, timeout_seconds: float) -> httpx.Client:
        # A new client per call: no connection to keep alive or close at shutdown.
        # The cost is tiny next to the seconds an answer takes.
        return httpx.Client(
            base_url=self._base_url, timeout=timeout_seconds, transport=self._transport
        )
