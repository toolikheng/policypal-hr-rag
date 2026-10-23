"""The question history: every answered (or refused) question, its sources and its vote.

Users are anonymous: a conversation is only a random UUID, so no names, emails or IP
addresses are stored. Question text is stored here (HR needs it for analytics) but is
never written to the logs.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from policypal.answering import Answer
from policypal.models import Conversation, DocumentChunk, Feedback, Message, MessageSource
from policypal.vocabulary import Channel, Rating


@dataclass(frozen=True)
class SavedAnswer:
    message_id: uuid.UUID
    conversation_id: uuid.UUID


def save_answer(
    engine: Engine,
    question: str,
    answer: Answer,
    *,
    conversation_id: uuid.UUID | None = None,
    channel: Channel,
) -> SavedAnswer:
    """Store a question, its answer and every retrieved source in one transaction.

    Without a conversation ID a new conversation is started. An ID the database doesn't
    know yet (e.g. made up by a client) is created rather than rejected.
    """
    conversation_id = conversation_id or uuid.uuid4()
    message_id = uuid.uuid4()
    reply = answer.reply
    with Session(engine) as session, session.begin():
        session.execute(
            insert(Conversation)
            .values(id=conversation_id, channel=channel)
            .on_conflict_do_nothing(index_elements=[Conversation.id])
        )
        session.add(
            Message(
                id=message_id,
                conversation_id=conversation_id,
                question=question,
                answer=reply.text,
                mode=reply.mode,
                fallback_reason=reply.fallback_reason,
                llm_model=reply.model,
                top_similarity=answer.top_similarity,
                retrieval_ms=answer.retrieval_ms,
                generation_ms=reply.generation_ms,
                total_ms=answer.total_ms,
            )
        )
        session.flush()  # the message row must exist before its sources point at it

        # A re-ingest may have deleted a chunk since it was retrieved. Its source is still
        # saved (title and section are a snapshot), just without the link.
        retrieved_ids = [source.chunk.chunk_id for source in answer.sources]
        still_there = set(
            session.scalars(select(DocumentChunk.id).where(DocumentChunk.id.in_(retrieved_ids)))
        )
        session.add_all(
            MessageSource(
                message_id=message_id,
                rank=source.rank,
                chunk_id=source.chunk.chunk_id if source.chunk.chunk_id in still_there else None,
                document_title=source.chunk.document_title,
                section=source.chunk.section,
                similarity=source.chunk.similarity,
                cited=source.cited,
            )
            for source in answer.sources
        )
    return SavedAnswer(message_id=message_id, conversation_id=conversation_id)


def record_feedback(
    engine: Engine, message_id: uuid.UUID, rating: Rating, comment: str | None
) -> bool:
    """Store the vote on an answer; voting again replaces the rating and comment.

    Returns False if no answer has this message ID.
    """
    upsert = insert(Feedback).values(message_id=message_id, rating=rating, comment=comment or None)
    # One statement, so two clicks at the same moment can't create two votes.
    upsert = upsert.on_conflict_do_update(
        index_elements=[Feedback.message_id],
        set_={
            "rating": upsert.excluded.rating,
            "comment": upsert.excluded.comment,
            "updated_at": func.now(),
        },
    )
    with Session(engine) as session, session.begin():
        if session.get(Message, message_id) is None:
            return False
        session.execute(upsert)
    return True
