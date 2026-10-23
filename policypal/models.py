"""Database tables, for use in queries. The migrations in migrations/versions/ own the
schema (constraints, indexes); these classes mirror the columns."""

import uuid
from datetime import datetime
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from policypal.embeddings import EMBEDDING_DIMENSION
from policypal.ingest.parsing import FileType

# Where a document came from: the sample policies folder, or an upload.
Origin = Literal["sample", "upload"]
# Which client asked a question.
Channel = Literal["ui", "widget", "api"]
Rating = Literal["up", "down"]


class Base(DeclarativeBase):
    pass


class Document(Base):
    """One policy file. `slug` (from the file name) identifies it across re-ingestion."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    source_filename: Mapped[str] = mapped_column(Text)
    file_type: Mapped[FileType] = mapped_column(Text)
    origin: Mapped[Origin] = mapped_column(Text)
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


class Conversation(Base):
    """An anonymous user's session: only a random UUID and the client it came from."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    channel: Mapped[Channel] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """One question and its answer, with how it was answered and how long each step took."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=func.gen_random_uuid()
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)  # answering.Mode
    fallback_reason: Mapped[str | None] = mapped_column(Text)  # answering.FallbackReason
    llm_model: Mapped[str | None] = mapped_column(Text)
    top_similarity: Mapped[float | None] = mapped_column(REAL)
    retrieval_ms: Mapped[int]
    generation_ms: Mapped[int | None]
    total_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageSource(Base):
    """A chunk retrieved for a message. The title and section are a snapshot, and
    chunk_id becomes NULL when a re-ingest deletes the chunk."""

    __tablename__ = "message_sources"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    document_title: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(REAL)
    cited: Mapped[bool]


class Feedback(Base):
    """The vote on a message: at most one per message."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[Rating] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
