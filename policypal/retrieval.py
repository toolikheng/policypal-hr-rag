"""Find the policy chunks most similar to a question (vector search with pgvector)."""

from dataclasses import dataclass

from sqlalchemy import Engine, select

from policypal.embeddings import Embedder
from policypal.models import Document, DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    document_title: str
    section: str
    section_path: str
    text: str
    # Cosine similarity of the question and chunk vectors: 1 means the same direction,
    # 0 means unrelated. It is a score for ranking, not a probability.
    similarity: float


def retrieve(engine: Engine, embedder: Embedder, question: str, top_k: int) -> list[RetrievedChunk]:
    """Return the `top_k` chunks closest to the question, best first."""
    query_vector = embedder.embed_query(question)
    # `<=>` is pgvector's cosine distance (1 - cosine similarity). Ordering by it with a
    # LIMIT lets PostgreSQL use the HNSW index from migration 0002.
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    query = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.title,
            DocumentChunk.section,
            DocumentChunk.section_path,
            DocumentChunk.content,
            distance.label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(distance)
        .limit(top_k)
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    return [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            section=row.section,
            section_path=row.section_path,
            text=row.content,
            similarity=1 - row.distance,
        )
        for row in rows
    ]
