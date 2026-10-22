"""Add the documents and chunks tables.

`chunks.embedding` is a pgvector column, so vector search and normal SQL (joins to
documents, filters) work in the same query. The HNSW index makes nearest-neighbour
search fast as the number of chunks grows; it is approximate, which is fine for search.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("source_filename", sa.Text, nullable=False),
        sa.Column("file_type", sa.Text, nullable=False),
        sa.Column("origin", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.CHAR(64), nullable=False),
        sa.Column("pipeline_version", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("file_type IN ('md', 'pdf')", name="documents_file_type_check"),
        sa.CheckConstraint("origin IN ('sample', 'upload')", name="documents_origin_check"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "document_id",
            sa.BigInteger,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.Text, nullable=False),
        sa.Column("section_path", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("word_count", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        # Also serves as the index for looking up a document's chunks (document_id first).
        sa.UniqueConstraint("document_id", "chunk_index", name="chunks_document_chunk_key"),
    )
    op.create_index(
        "chunks_embedding_hnsw_idx",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
