"""Analytics over the question history: what staff ask, what the policies don't answer,
how answers are rated, and how long they take.

Everything is computed in SQL from the messages stored in the last `days` days. A rate is
None when there is nothing to divide by, so an empty period never shows "0% helpful".
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Connection, Engine, Select, func, select

from policypal.models import Feedback, Message

# How many questions the "top" and "unanswered" lists show.
TOP_LIMIT = 10


@dataclass(frozen=True)
class FeedbackStats:
    count: int
    up: int
    down: int
    feedback_rate: float | None  # messages with a vote / all messages
    helpful_rate: float | None  # up / votes


@dataclass(frozen=True)
class LatencyStats:
    """Average total time to answer, in milliseconds."""

    overall: int | None
    llm: int | None
    extractive: int | None


@dataclass(frozen=True)
class QuestionCount:
    question: str  # lower-cased and trimmed, so "Leave?" and " leave? " count as one
    count: int
    last_asked: datetime


@dataclass(frozen=True)
class FallbackCount:
    reason: str  # as stored, e.g. llm_timeout; may be a reason the code no longer has
    count: int


@dataclass(frozen=True)
class Analytics:
    period_days: int
    total_questions: int
    answered: int  # mode llm or extractive
    refused: int
    refusal_rate: float | None
    feedback: FeedbackStats
    avg_latency_ms: LatencyStats
    top_questions: tuple[QuestionCount, ...]
    unanswered_questions: tuple[QuestionCount, ...]  # the refused ones
    fallbacks: tuple[FallbackCount, ...]  # answers that fell back to quoting the policy


def summarize(engine: Engine, days: int) -> Analytics:
    """Analytics for the messages asked in the last `days` days."""
    in_period = Message.created_at >= datetime.now(UTC) - timedelta(days=days)
    with engine.connect() as conn:
        totals = conn.execute(_totals(in_period)).one()
        top = _question_counts(conn, in_period)
        unanswered = _question_counts(conn, in_period, Message.mode == "refused")
        fallbacks = _fallbacks(conn, in_period)
    return Analytics(
        period_days=days,
        total_questions=totals.total,
        answered=totals.total - totals.refused,
        refused=totals.refused,
        refusal_rate=_rate(totals.refused, totals.total),
        feedback=FeedbackStats(
            count=totals.votes,
            up=totals.up,
            down=totals.down,
            feedback_rate=_rate(totals.votes, totals.total),
            helpful_rate=_rate(totals.up, totals.votes),
        ),
        avg_latency_ms=LatencyStats(
            overall=_ms(totals.avg_ms),
            llm=_ms(totals.avg_llm_ms),
            extractive=_ms(totals.avg_extractive_ms),
        ),
        top_questions=top,
        unanswered_questions=unanswered,
        fallbacks=fallbacks,
    )


def _totals(in_period: ColumnElement[bool]) -> Select[Any]:
    """One row of counts and averages. A message has at most one vote, so joining the
    votes doesn't count any message twice."""
    return (
        select(
            func.count().label("total"),
            func.count().filter(Message.mode == "refused").label("refused"),
            func.count(Feedback.id).label("votes"),
            func.count().filter(Feedback.rating == "up").label("up"),
            func.count().filter(Feedback.rating == "down").label("down"),
            func.avg(Message.total_ms).label("avg_ms"),
            func.avg(Message.total_ms).filter(Message.mode == "llm").label("avg_llm_ms"),
            func.avg(Message.total_ms)
            .filter(Message.mode == "extractive")
            .label("avg_extractive_ms"),
        )
        .select_from(Message)
        .outerjoin(Feedback, Feedback.message_id == Message.id)
        .where(in_period)
    )


def _question_counts(
    conn: Connection, in_period: ColumnElement[bool], *where: ColumnElement[bool]
) -> tuple[QuestionCount, ...]:
    """The most asked questions, most asked first; ties go to the most recent."""
    question = func.lower(func.trim(Message.question)).label("question")
    count = func.count().label("count")
    last_asked = func.max(Message.created_at).label("last_asked")
    query = (
        select(question, count, last_asked)
        .where(in_period, *where)
        .group_by(question)
        .order_by(count.desc(), last_asked.desc(), question)
        .limit(TOP_LIMIT)
    )
    return tuple(
        QuestionCount(row.question, row.count, row.last_asked) for row in conn.execute(query)
    )


def _fallbacks(conn: Connection, in_period: ColumnElement[bool]) -> tuple[FallbackCount, ...]:
    """Fallbacks by reason. Extractive answers without a reason (no LLM configured) are
    not fallbacks, so they aren't counted."""
    count = func.count().label("count")
    query = (
        select(Message.fallback_reason, count)
        .where(in_period, Message.fallback_reason.is_not(None))
        .group_by(Message.fallback_reason)
        .order_by(count.desc(), Message.fallback_reason)
    )
    return tuple(FallbackCount(reason, count) for reason, count in conn.execute(query))


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _ms(average: Decimal | None) -> int | None:
    return None if average is None else round(average)
