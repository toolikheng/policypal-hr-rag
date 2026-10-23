"""Test doubles. They live in tests/ only, so the application can never use them."""

import hashlib
import math
import re
from collections.abc import Sequence

from policypal.embeddings import EMBEDDING_DIMENSION
from policypal.llm.base import LLMError, LLMStatus
from policypal.retrieval import RetrievedChunk


class FakeEmbedder:
    """Deterministic, offline stand-in for the real embedding model.

    Each word is hashed into one of `dimension` buckets ("bag of words"), so texts that
    share words get similar vectors. Every embedded text and question is recorded, so
    tests can check what was (or wasn't) embedded.
    """

    def __init__(
        self, model_name: str = "fake-embedder", dimension: int = EMBEDDING_DIMENSION
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.embedded_texts: list[str] = []
        self.embedded_queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [self._embed(text) for text in texts]

    def embed_query(self, question: str) -> list[float]:
        self.embedded_queries.append(question)
        return self._embed(question)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dimension
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class FakeLLM:
    """Deterministic stand-in for an LLM provider, used only in tests.

    It returns a scripted reply (or raises a scripted LLMError) and records every call,
    so tests can check what the model was given without running a model.
    """

    name = "fake"

    def __init__(
        self,
        reply: str = "Employees get 16 days of annual leave [1].",
        *,
        error: LLMError | None = None,
        status: LLMStatus = "ok",
        model: str = "fake-model",
    ) -> None:
        self.reply = reply
        self.error = error
        self.model = model
        self._status: LLMStatus = status
        self.calls: list[tuple[str, list[RetrievedChunk]]] = []

    def generate(self, question: str, excerpts: Sequence[RetrievedChunk]) -> str:
        self.calls.append((question, list(excerpts)))
        if self.error is not None:
            raise self.error
        return self.reply

    def status(self) -> LLMStatus:
        return self._status


class FakeApiClient:
    """Stand-in for ui.api_client.PolicyPalClient in Streamlit page tests.

    Replies are scripted; every call is recorded in `calls`.
    """

    def __init__(
        self,
        *,
        health: dict | Exception | None = None,  # an exception is raised by health()
        answers: list[dict] | None = None,
        documents: dict[int, dict] | None = None,
        uploads: list[dict | Exception] | None = None,
    ) -> None:
        self._health = health or {"status": "ok", "database": "ok", "version": "0.1.0"}
        self.answers = list(answers or [])
        self.documents = documents or {}
        self.uploads = list(uploads or [])
        self.calls: list[tuple] = []

    def _next(self, replies: list) -> object:
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def health(self) -> dict:
        if isinstance(self._health, Exception):
            raise self._health
        return self._health

    def ask(self, question: str, conversation_id: str | None = None) -> dict:
        self.calls.append(("ask", question, conversation_id))
        return self._next(self.answers)  # type: ignore[return-value]

    def feedback(self, message_id: str, rating: str, comment: str | None = None) -> None:
        self.calls.append(("feedback", message_id, rating, comment))

    def list_documents(self) -> list[dict]:
        self.calls.append(("list_documents",))
        return [
            {key: value for key, value in doc.items() if key != "sections"}
            for doc in self.documents.values()
        ]

    def get_document(self, document_id: int) -> dict:
        self.calls.append(("get_document", document_id))
        return self.documents[document_id]

    def upload(self, filename: str, data: bytes, *, token: str, replace: bool = False) -> dict:
        self.calls.append(("upload", filename, data, token, replace))
        return self._next(self.uploads)  # type: ignore[return-value]

    def reingest(self, *, token: str) -> list[dict]:
        self.calls.append(("reingest", token))
        return [{"slug": "leave-policy", "status": "unchanged", "chunks": 20}]
