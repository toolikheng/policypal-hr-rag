"""Test doubles. They live in tests/ only, so the application can never use them."""

import hashlib
import math
import re

from policypal.embeddings import EMBEDDING_DIMENSION


class FakeEmbedder:
    """Deterministic, offline stand-in for the real embedding model.

    Each word is hashed into one of `dimension` buckets ("bag of words"), so texts that
    share words get similar vectors. Every embedded text is recorded, so tests can check
    what was (or wasn't) embedded.
    """

    def __init__(
        self, model_name: str = "fake-embedder", dimension: int = EMBEDDING_DIMENSION
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.embedded_texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dimension
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
