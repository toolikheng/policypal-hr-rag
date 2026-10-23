"""Analytics calculations (policypal.analytics) on an empty and a seeded database.

The seeded numbers are worked out by hand in the comments, so each assertion can be
checked without running anything.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Connection, Engine, text

from policypal.analytics import (
    TOP_LIMIT,
    Analytics,
    FallbackCount,
    FeedbackStats,
    LatencyStats,
    summarize,
)


def seed(
    conn: Connection,
    question: str,
    mode: str,
    total_ms: int,
    *,
    reason: str | None = None,
    rating: str | None = None,
    days_ago: float = 0,
) -> None:
    conversation_id = conn.execute(
        text("INSERT INTO conversations (channel) VALUES ('ui') RETURNING id")
    ).scalar_one()
    message_id = conn.execute(
        text(
            "INSERT INTO messages (conversation_id, question, answer, mode, fallback_reason,"
            " retrieval_ms, total_ms, created_at) VALUES (:conversation_id, :question, 'a',"
            " :mode, :reason, 10, :total_ms, :created_at) RETURNING id"
        ),
        {
            "conversation_id": conversation_id,
            "question": question,
            "mode": mode,
            "reason": reason,
            "total_ms": total_ms,
            "created_at": datetime.now(UTC) - timedelta(days=days_ago),
        },
    ).scalar_one()
    if rating:
        conn.execute(
            text("INSERT INTO feedback (message_id, rating) VALUES (:id, :rating)"),
            {"id": message_id, "rating": rating},
        )


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    """9 messages in the last 30 days, plus 2 older ones."""
    with engine.begin() as conn:
        # Asked 3 times (different case and spaces): 2 LLM answers and a timeout fallback.
        seed(conn, "How much annual leave?", "llm", 1000, rating="up", days_ago=3)
        seed(conn, "  how much ANNUAL leave? ", "llm", 3000, rating="down", days_ago=2)
        seed(conn, "How much annual leave?", "extractive", 600, reason="llm_timeout", days_ago=1)
        # Refused 3 times: twice for the bonus, once for the cat.
        seed(conn, "Is there a bonus?", "refused", 50, rating="down", days_ago=5)
        seed(conn, "is there a bonus?", "refused", 50, days_ago=4)
        seed(conn, "Can I bring my cat?", "refused", 100, days_ago=6)
        seed(conn, "What is the overtime rate?", "extractive", 400, reason="llm_timeout",
             rating="up", days_ago=7)  # fmt: skip
        seed(conn, "Dress code?", "extractive", 200, reason="llm_unavailable", days_ago=8)
        # Extractive because no LLM is configured: not a fallback.
        seed(conn, "Medical leave?", "extractive", 100, days_ago=9)
        # Older than 30 days.
        seed(conn, "Old question?", "refused", 40, rating="up", days_ago=40)
        seed(conn, "Old fallback?", "extractive", 900, reason="llm_timeout", days_ago=45)
    return engine


def test_an_empty_database_gives_zeros_and_nulls(engine: Engine) -> None:
    """Rates are null, not 0: with no answers there is nothing to divide by."""
    assert summarize(engine, days=30) == Analytics(
        period_days=30,
        total_questions=0,
        answered=0,
        refused=0,
        refusal_rate=None,
        feedback=FeedbackStats(count=0, up=0, down=0, feedback_rate=None, helpful_rate=None),
        avg_latency_ms=LatencyStats(overall=None, llm=None, extractive=None),
        top_questions=(),
        unanswered_questions=(),
        fallbacks=(),
    )


def test_counts_and_refusal_rate(seeded: Engine) -> None:
    result = summarize(seeded, days=30)

    assert (result.total_questions, result.answered, result.refused) == (9, 6, 3)
    assert result.refusal_rate == pytest.approx(3 / 9, abs=1e-4)


def test_feedback_rates(seeded: Engine) -> None:
    # Votes in the period: 2 up, 2 down, on 4 of the 9 messages.
    assert summarize(seeded, days=30).feedback == FeedbackStats(
        count=4, up=2, down=2, feedback_rate=pytest.approx(4 / 9, abs=1e-4), helpful_rate=0.5
    )


def test_average_latency_per_mode(seeded: Engine) -> None:
    # overall (1000+3000+600+50+50+100+400+200+100) / 9 = 611.1; llm 2000;
    # extractive (600+400+200+100) / 4 = 325.
    assert summarize(seeded, days=30).avg_latency_ms == LatencyStats(
        overall=611, llm=2000, extractive=325
    )


def test_top_questions_are_grouped_after_lower_casing_and_trimming(seeded: Engine) -> None:
    top = summarize(seeded, days=30).top_questions

    assert [(q.question, q.count) for q in top[:2]] == [
        ("how much annual leave?", 3),
        ("is there a bonus?", 2),
    ]
    assert len(top) == 6
    # Ties are ordered by the most recently asked.
    assert [q.question for q in top[2:]] == [
        "can i bring my cat?",
        "what is the overtime rate?",
        "dress code?",
        "medical leave?",
    ]
    assert top[0].last_asked > top[1].last_asked


def test_unanswered_questions_are_the_refused_ones(seeded: Engine) -> None:
    unanswered = summarize(seeded, days=30).unanswered_questions

    assert [(q.question, q.count) for q in unanswered] == [
        ("is there a bonus?", 2),
        ("can i bring my cat?", 1),
    ]


def test_fallbacks_are_counted_by_reason(seeded: Engine) -> None:
    """Owner addition: answers that fell back to quoting the policy, by fallback_reason.
    Extractive answers with no reason (no LLM configured) are not fallbacks."""
    assert summarize(seeded, days=30).fallbacks == (
        FallbackCount(reason="llm_timeout", count=2),
        FallbackCount(reason="llm_unavailable", count=1),
    )


def test_a_longer_period_includes_older_messages(seeded: Engine) -> None:
    result = summarize(seeded, days=60)

    assert (result.period_days, result.total_questions, result.refused) == (60, 11, 4)
    assert result.feedback.count == 5
    assert result.fallbacks[0] == FallbackCount(reason="llm_timeout", count=3)


def test_question_lists_are_capped(engine: Engine) -> None:
    with engine.begin() as conn:
        for number in range(TOP_LIMIT + 2):
            seed(conn, f"Question {number}?", "refused", 10)

    result = summarize(engine, days=30)

    assert len(result.top_questions) == len(result.unanswered_questions) == TOP_LIMIT
