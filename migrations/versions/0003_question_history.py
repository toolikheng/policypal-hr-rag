"""Add the question history: conversations, messages, message_sources and feedback.

- A conversation is only a random UUID: no names, emails or IP addresses are stored.
- A message is one question and its answer, with the mode and the time each step took.
- message_sources keeps every retrieved chunk with its rank and whether it was cited.
  The document title and section are copied in (a snapshot), and chunk_id becomes NULL
  when a re-ingest deletes the chunk, so old answers keep their sources.
- feedback holds at most one vote per message; voting again updates it.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("channel", sa.Text, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "channel IN ('ui', 'widget', 'api')", name="conversations_channel_check"
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column(
            "conversation_id",
            UUID,
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("fallback_reason", sa.Text),
        sa.Column("llm_model", sa.Text),
        sa.Column("top_similarity", sa.REAL),
        sa.Column("retrieval_ms", sa.Integer, nullable=False),
        sa.Column("generation_ms", sa.Integer),
        sa.Column("total_ms", sa.Integer, nullable=False),
        _created_at(),
        sa.CheckConstraint("mode IN ('llm', 'extractive', 'refused')", name="messages_mode_check"),
    )
    # Analytics filters messages by period ("the last 30 days").
    op.create_index("messages_created_at_idx", "messages", ["created_at"])
    op.create_table(
        "message_sources",
        sa.Column(
            "message_id",
            UUID,
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rank", sa.SmallInteger, primary_key=True),
        sa.Column("chunk_id", sa.BigInteger, sa.ForeignKey("chunks.id", ondelete="SET NULL")),
        sa.Column("document_title", sa.Text, nullable=False),
        sa.Column("section", sa.Text, nullable=False),
        sa.Column("similarity", sa.REAL, nullable=False),
        sa.Column("cited", sa.Boolean, nullable=False),
    )
    # Each deleted chunk looks up the sources that point at it; without this index a
    # re-ingest would scan the whole table once per chunk.
    op.create_index("message_sources_chunk_id_idx", "message_sources", ["chunk_id"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "message_id",
            UUID,
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("rating", sa.Text, nullable=False),
        sa.Column("comment", sa.Text),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("rating IN ('up', 'down')", name="feedback_rating_check"),
        sa.CheckConstraint("char_length(comment) <= 500", name="feedback_comment_length_check"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("message_sources")
    op.drop_table("messages")
    op.drop_table("conversations")
