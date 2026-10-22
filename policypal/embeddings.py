"""Embedding model: turns text into vectors whose directions capture meaning."""

from typing import Protocol

from policypal.config import Settings

# Must match the vector(384) column created by migration 0002.
EMBEDDING_DIMENSION = 384


class Embedder(Protocol):
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, question: str) -> list[float]: ...


def build_embedder(settings: Settings) -> "SentenceTransformerEmbedder":
    """The real embedder, configured from settings (used by the API and the ingest CLI)."""
    return SentenceTransformerEmbedder(
        settings.embedding_model, query_instruction=settings.embedding_query_instruction
    )


class SentenceTransformerEmbedder:
    """A local sentence-transformers model, run on CPU.

    The Docker image downloads the model once at build time, so no internet access or
    API key is needed at run time. Vectors are normalised to length 1, so cosine
    similarity between two vectors is simply their dot product.

    Questions and passages are embedded differently: a question gets `query_instruction`
    in front of it (passages never do), which helps the model match a short question to
    a long passage.
    """

    def __init__(self, model_name: str, *, query_instruction: str) -> None:
        # Imported here: loading torch takes seconds, and the tests use a fake embedder.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.query_instruction = query_instruction
        self._model = SentenceTransformer(model_name, device="cpu")
        self.dimension = self._model.get_embedding_dimension()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode_document(
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False
        )
        return vectors.tolist()

    def embed_query(self, question: str) -> list[float]:
        # An explicit prompt (even "") replaces any default prompt the model defines.
        vector = self._model.encode_query(
            question, prompt=self.query_instruction, normalize_embeddings=True
        )
        return vector.tolist()
