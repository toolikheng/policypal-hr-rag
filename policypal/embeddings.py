"""Embedding model: turns text into vectors whose directions capture meaning."""

from typing import Protocol

# Must match the vector(384) column created by migration 0002.
EMBEDDING_DIMENSION = 384


class Embedder(Protocol):
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """A local sentence-transformers model, run on CPU.

    The Docker image downloads the model once at build time, so no internet access or
    API key is needed at run time. Vectors are normalised to length 1, so cosine
    similarity between two vectors is simply their dot product.
    """

    def __init__(self, model_name: str) -> None:
        # Imported here: loading torch takes seconds, and the tests use a fake embedder.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")
        self.dimension = self._model.get_embedding_dimension()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode_document(
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False
        )
        return vectors.tolist()
