"""Database tables, for use in queries. The migrations in migrations/versions/ own the
schema (constraints, indexes); these classes mirror the columns."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from policypal.embeddings import EMBEDDING_DIMENSION


class Base(DeclarativeBase):
    pass


class Document(Base):
    """One policy file. `slug` (from the file name) identifies it across re-ingestion."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    source_filename: Mapped[str] = mapped_column(Text)
    file_type: Mapped[str] = mapped_column(Text)  # "md" or "pdf"
    origin: Mapped[str] = mapped_column(Text)  # "sample" or "upload"
    content_sha256: Mapped[str] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    """One searchable piece of a document, with its section and embedding vector."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    section: Mapped[str] = mapped_column(Text)
    section_path: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
