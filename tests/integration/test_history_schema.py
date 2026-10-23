"""Migration 0003: the question history tables (conversations, messages, sources, feedback).

The migration owns the rules, so these tests use plain SQL against the real database.
"""

import uuid

import pytest
from alembic import command
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.helpers import alembic_config

HISTORY_TABLES = {"conversations", "messages", "message_sources", "feedback"}


def add_chunk(conn: Connection) -> int:
    document_id = conn.execute(
        text(
            "INSERT INTO documents (slug, title, source_filename, file_type, origin,"
            " content_sha256, pipeline_version) VALUES"
            " ('leave-policy', 'Leave Policy', 'leave-policy.md', 'md', 'sample',"
            " repeat('0', 64), 'v') RETURNING id"
        )
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO chunks (document_id, chunk_index, section, section_path, content,"
            " word_count, embedding) VALUES (:document_id, 0, '4.1 Annual Leave',"
            " '4. Leave > 4.1 Annual Leave', 'Sixteen days.', 2,"
            " array_fill(0.1, ARRAY[384])::vector) RETURNING id"
        ),
        {"document_id": document_id},
    ).scalar_one()


def add_message(conn: Connection, *, mode: str = "llm", channel: str = "ui") -> uuid.UUID:
    conversation_id = conn.execute(
        text("INSERT INTO conversations (channel) VALUES (:channel) RETURNING id"),
        {"channel": channel},
    ).scalar_one()
    return conn.execute(
        text(
            "INSERT INTO messages (conversation_id, question, answer, mode, retrieval_ms,"
            " total_ms) VALUES (:conversation_id, 'How much leave?', 'Sixteen days [1].',"
            " :mode, 40, 900) RETURNING id"
        ),
        {"conversation_id": conversation_id, "mode": mode},
    ).scalar_one()


def add_source(conn: Connection, message_id: uuid.UUID, chunk_id: int | None, rank: int = 1):
    conn.execute(
        text(
            "INSERT INTO message_sources (message_id, rank, chunk_id, document_title, section,"
            " similarity, cited) VALUES (:message_id, :rank, :chunk_id, 'Leave Policy',"
            " '4.1 Annual Leave', 0.81, true)"
        ),
        {"message_id": message_id, "rank": rank, "chunk_id": chunk_id},
    )


def add_feedback(conn: Connection, message_id: uuid.UUID, rating: str = "up", comment=None):
    conn.execute(
        text("INSERT INTO feedback (message_id, rating, comment) VALUES (:id, :rating, :comment)"),
        {"id": message_id, "rating": rating, "comment": comment},
    )


def count(conn: Connection, table: str) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608


def test_history_tables_exist_with_random_uuid_ids(engine: Engine) -> None:
    assert HISTORY_TABLES <= set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        message_id = add_message(conn)
    assert isinstance(message_id, uuid.UUID)


def test_messages_are_indexed_by_time_for_the_analytics_period(engine: Engine) -> None:
    indexes = {
        index["name"]: index["column_names"] for index in inspect(engine).get_indexes("messages")
    }
    assert ["created_at"] in indexes.values()


def test_sources_are_indexed_by_chunk_so_reingest_deletes_stay_fast(engine: Engine) -> None:
    indexes = inspect(engine).get_indexes("message_sources")
    assert ["chunk_id"] in [index["column_names"] for index in indexes]


@pytest.mark.parametrize(
    ("statement", "params"),
    [
        ("INSERT INTO conversations (channel) VALUES ('email')", {}),
        (
            "INSERT INTO messages (conversation_id, question, answer, mode, retrieval_ms,"
            " total_ms) VALUES ((SELECT id FROM conversations LIMIT 1), 'q', 'a', 'guess', 1, 1)",
            {},
        ),
        ("INSERT INTO feedback (message_id, rating) VALUES (:message_id, 'meh')", {}),
        (
            "INSERT INTO feedback (message_id, rating, comment)"
            " VALUES (:message_id, 'down', repeat('x', 501))",
            {},
        ),
    ],
    ids=["channel", "mode", "rating", "comment-too-long"],
)
def test_invalid_values_are_rejected(engine: Engine, statement: str, params: dict) -> None:
    with engine.begin() as conn:
        message_id = add_message(conn)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(statement), {"message_id": message_id, **params})


def test_one_vote_per_message(engine: Engine) -> None:
    with engine.begin() as conn:
        message_id = add_message(conn)
        add_feedback(conn, message_id, "up")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        add_feedback(conn, message_id, "down")


def test_one_source_per_rank(engine: Engine) -> None:
    with engine.begin() as conn:
        message_id = add_message(conn)
        add_source(conn, message_id, chunk_id=None, rank=1)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        add_source(conn, message_id, chunk_id=None, rank=1)


def test_deleting_a_chunk_keeps_the_source_snapshot(engine: Engine) -> None:
    """Re-ingesting a policy replaces its chunks; the answer history must survive."""
    with engine.begin() as conn:
        chunk_id = add_chunk(conn)
        message_id = add_message(conn)
        add_source(conn, message_id, chunk_id)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM documents"))  # cascades to its chunks

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT chunk_id, document_title, section, similarity FROM message_sources")
        ).one()
    assert row.chunk_id is None
    assert (row.document_title, row.section) == ("Leave Policy", "4.1 Annual Leave")
    assert row.similarity == pytest.approx(0.81)


def test_deleting_a_conversation_deletes_its_messages_sources_and_votes(engine: Engine) -> None:
    with engine.begin() as conn:
        message_id = add_message(conn)
        add_source(conn, message_id, chunk_id=None)
        add_feedback(conn, message_id)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM conversations"))
        remaining = {table: count(conn, table) for table in HISTORY_TABLES}
    assert remaining == dict.fromkeys(HISTORY_TABLES, 0)


def test_downgrade_one_step_drops_only_the_history_tables(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    try:
        command.downgrade(config, "0002")
        check = create_engine(migrated_database_url)
        try:
            tables = set(inspect(check).get_table_names())
        finally:
            check.dispose()
        assert not tables & HISTORY_TABLES
        assert {"documents", "chunks"} <= tables
    finally:
        command.upgrade(config, "head")
