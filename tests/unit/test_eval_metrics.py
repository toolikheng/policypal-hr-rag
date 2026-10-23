"""Evaluation metrics, checked on small hand-made examples (no database, no model)."""

import pytest

from evaluation.metrics import (
    THRESHOLD_GRID,
    AnswerOutcome,
    Match,
    Rate,
    RefusalCounts,
    RetrievalOutcome,
    Section,
    SweepRow,
    all_found_rate,
    answer_problems,
    choose_threshold,
    count_refusals,
    document_rank,
    expected_source_cited_rate,
    group_by_type,
    hit_rate,
    instruction_verdict,
    refused_at,
    reply_breakdown,
    retrieval_problems,
    section_rank,
    summarize_latency,
    sweep,
)
from policypal.answering import build_reply
from tests.helpers import retrieved_chunk

ANNUAL = Section("leave-policy", "4.1 Annual Leave Entitlement")
CARRY = Section("leave-policy", "4.3 Carry Forward of Annual Leave")
SICK = Section("leave-policy", "6. Medical Leave")
OUTPATIENT = Section("medical-claims-policy", "4. Outpatient Treatment")
MILEAGE = Section("expense-claims-policy", "3.1 Mileage")


def search(
    expected: tuple[Section, ...] = (),
    retrieved: tuple[Section, ...] = (),
    *,
    similarities: tuple[float, ...] | None = None,
    question_type: str = "plain",
    question_id: str = "q1",
    retrieval_ms: int = 50,
) -> RetrievalOutcome:
    """One question's search results; the similarities fall by 0.05 per rank unless given."""
    if similarities is None:
        similarities = tuple(0.80 - 0.05 * index for index in range(len(retrieved)))
    return RetrievalOutcome(
        question_id=question_id,
        question_type=question_type,
        expected=expected,
        retrieved=tuple(Match(s, sim) for s, sim in zip(retrieved, similarities, strict=True)),
        retrieval_ms=retrieval_ms,
    )


def answered(
    mode: str = "llm",
    *,
    expected: tuple[Section, ...] = (ANNUAL,),
    cited: tuple[Section, ...] = (ANNUAL,),
    fallback_reason: str | None = None,
    generation_ms: int | None = 9000,
    total_ms: int = 9100,
    top_similarity: float = 0.8,
    question_type: str = "plain",
) -> AnswerOutcome:
    """One question's answer from the full pipeline."""
    return AnswerOutcome(
        question_id="q1",
        question_type=question_type,
        expected=expected,
        mode=mode,
        answer="An answer [1].",
        cited=cited,
        fallback_reason=fallback_reason,
        retrieved=(Match(ANNUAL, top_similarity),),
        retrieval_ms=40,
        generation_ms=generation_ms,
        total_ms=total_ms,
    )


# --- Retrieval: ranks and hit rates -------------------------------------------------


def test_section_rank_is_the_rank_of_the_first_expected_section() -> None:
    outcome = search(expected=(CARRY,), retrieved=(ANNUAL, SICK, CARRY, CARRY))

    assert section_rank(outcome) == 3


def test_any_expected_section_counts_and_none_found_gives_no_rank() -> None:
    assert section_rank(search(expected=(OUTPATIENT, SICK), retrieved=(ANNUAL, SICK))) == 2
    assert section_rank(search(expected=(OUTPATIENT,), retrieved=(ANNUAL, SICK))) is None


def test_document_rank_accepts_any_section_of_an_expected_policy() -> None:
    outcome = search(expected=(CARRY,), retrieved=(OUTPATIENT, ANNUAL))

    assert section_rank(outcome) is None
    assert document_rank(outcome) == 2


def test_hit_rate_at_k_counts_answerable_questions_found_in_the_top_k() -> None:
    outcomes = [
        search(expected=(ANNUAL,), retrieved=(ANNUAL, SICK)),  # rank 1
        search(expected=(CARRY,), retrieved=(ANNUAL, CARRY)),  # rank 2
        search(expected=(OUTPATIENT,), retrieved=(ANNUAL, SICK)),  # not found
        search(expected=(), retrieved=(ANNUAL,)),  # unanswerable: not counted
    ]

    assert hit_rate(outcomes, k=1) == Rate(1, 3)
    assert hit_rate(outcomes, k=3) == Rate(2, 3)
    assert hit_rate(outcomes, k=3, level="document") == Rate(2, 3)


def test_document_level_hit_rate_is_more_lenient_than_section_level() -> None:
    outcomes = [search(expected=(CARRY,), retrieved=(ANNUAL, SICK))]

    assert hit_rate(outcomes, k=5) == Rate(0, 1)
    assert hit_rate(outcomes, k=5, level="document") == Rate(1, 1)


def test_all_found_rate_needs_every_expected_section_in_the_top_k() -> None:
    both_needed = search(expected=(OUTPATIENT, SICK), retrieved=(SICK, ANNUAL, OUTPATIENT))

    assert hit_rate([both_needed], k=2) == Rate(1, 1)
    assert all_found_rate([both_needed], k=2) == Rate(0, 1)
    assert all_found_rate([both_needed], k=3) == Rate(1, 1)


def test_group_by_type_keeps_answerable_questions_in_report_order() -> None:
    table = search(expected=(ANNUAL,), question_type="table", question_id="t")
    plain = search(expected=(ANNUAL,), question_type="plain", question_id="p")
    two = search(expected=(ANNUAL, SICK), question_type="two-section", question_id="2")
    refusal = search(expected=(), question_type="uncovered-topic", question_id="u")

    groups = group_by_type([two, table, refusal, plain])

    assert list(groups) == ["plain", "table", "two-section"]
    assert groups["table"] == [table]


def test_rate_reads_as_a_count_and_a_percentage() -> None:
    assert Rate(37, 40).value == pytest.approx(0.925)
    assert str(Rate(37, 40)) == "37/40 (92.5%)"
    assert Rate(0, 0).value is None
    assert str(Rate(0, 0)) == "n/a"


# --- Refusals and the threshold sweep -----------------------------------------------


@pytest.mark.parametrize(
    ("top_similarity", "expected"),
    [(0.64, True), (0.65, False), (0.66, False), (None, True)],
)
def test_refused_at_is_the_apps_own_rule(top_similarity: float | None, expected: bool) -> None:
    retrieved = [] if top_similarity is None else [retrieved_chunk(similarity=top_similarity)]
    app_refused = build_reply("q", retrieved, llm=None, min_similarity=0.65).mode == "refused"

    assert refused_at(top_similarity, 0.65) is expected
    assert app_refused is expected


def test_count_refusals_fills_the_four_cells() -> None:
    # (answerable, refused) per question
    counts = count_refusals(
        [(True, False), (True, False), (True, True), (False, True), (False, False)]
    )

    assert counts == RefusalCounts(answered=2, false_refusals=1, refused=1, false_answers=1)
    assert counts.total == 5
    assert counts.accuracy == pytest.approx(3 / 5)
    # The mean of 2/3 answerable answered and 1/2 unanswerable refused.
    assert counts.balanced_accuracy == pytest.approx((2 / 3 + 1 / 2) / 2)


def test_balanced_accuracy_is_not_fooled_by_the_bigger_group() -> None:
    # Answering everything: 10 of 12 right, but no unanswerable question is refused.
    counts = count_refusals([(True, False)] * 10 + [(False, False)] * 2)

    assert counts.accuracy == pytest.approx(10 / 12)
    assert counts.balanced_accuracy == pytest.approx(0.5)


def test_balanced_accuracy_uses_only_the_groups_present() -> None:
    assert count_refusals([(True, False), (True, True)]).balanced_accuracy == pytest.approx(0.5)
    assert count_refusals([]).accuracy is None
    assert count_refusals([]).balanced_accuracy is None


def test_the_threshold_grid_is_0_50_to_0_85_in_steps_of_0_01() -> None:
    assert len(THRESHOLD_GRID) == 36
    assert THRESHOLD_GRID[0] == 0.50
    assert THRESHOLD_GRID[-1] == 0.85
    assert 0.63 in THRESHOLD_GRID  # exact two-decimal values, no 0.6300000000000001


def test_sweep_rescores_the_same_similarities_at_each_threshold() -> None:
    outcomes = [
        search(expected=(ANNUAL,), retrieved=(ANNUAL,), similarities=(0.70,)),
        search(expected=(), retrieved=(SICK,), similarities=(0.60,)),
    ]

    rows = sweep(outcomes, thresholds=(0.55, 0.65, 0.75))

    assert [row.threshold for row in rows] == [0.55, 0.65, 0.75]
    assert rows[0].counts == RefusalCounts(answered=1, false_refusals=0, refused=0, false_answers=1)
    assert rows[1].counts == RefusalCounts(answered=1, false_refusals=0, refused=1, false_answers=0)
    assert rows[2].counts == RefusalCounts(answered=0, false_refusals=1, refused=1, false_answers=0)


def _row(threshold: float, answered: int, refused: int) -> SweepRow:
    """A sweep row with 4 answerable and 4 unanswerable questions."""
    return SweepRow(threshold, RefusalCounts(answered, 4 - answered, refused, 4 - refused))


def test_choose_threshold_takes_the_best_balanced_accuracy() -> None:
    rows = [_row(0.60, 4, 2), _row(0.61, 4, 4), _row(0.62, 3, 4)]

    assert choose_threshold(rows) == 0.61


def test_choose_threshold_takes_the_middle_of_a_tied_range() -> None:
    rows = [_row(0.60, 4, 3), _row(0.61, 4, 4), _row(0.62, 4, 4), _row(0.63, 4, 4)]
    rows += [_row(0.64, 4, 4), _row(0.65, 3, 4)]

    assert choose_threshold(rows) == 0.625  # middle of 0.61 to 0.64


def test_choose_threshold_prefers_the_longest_tied_run_then_the_lowest() -> None:
    # Two separate best runs: 0.60-0.61 and 0.63-0.65. The longer one wins.
    rows = [_row(0.60, 4, 4), _row(0.61, 4, 4), _row(0.62, 3, 3)]
    rows += [_row(0.63, 4, 4), _row(0.64, 4, 4), _row(0.65, 4, 4)]
    assert choose_threshold(rows) == 0.64

    # Two best runs of the same length: the lower one wins (fewer false refusals).
    rows = [_row(0.60, 4, 4), _row(0.61, 3, 3), _row(0.62, 4, 4)]
    assert choose_threshold(rows) == 0.60


# --- Latency ------------------------------------------------------------------------


def test_summarize_latency_gives_mean_median_and_max() -> None:
    summary = summarize_latency([100, 300, 200, 50000])

    assert summary is not None
    assert summary.count == 4
    assert summary.mean_ms == pytest.approx(12650)
    assert summary.median_ms == pytest.approx(250)  # one slow cold start barely moves it
    assert summary.max_ms == 50000
    assert summarize_latency([]) is None


# --- End to end ---------------------------------------------------------------------


def test_reply_breakdown_separates_how_each_reply_was_made() -> None:
    outcomes = [
        answered("llm"),
        answered("llm"),
        answered("refused", cited=(), generation_ms=8000),  # the LLM refused
        answered("refused", cited=(), generation_ms=None, top_similarity=0.5),  # threshold
        answered("extractive", fallback_reason="llm_no_valid_citation"),
        answered("extractive", fallback_reason="llm_timeout", generation_ms=120000),
        answered("extractive", generation_ms=None),  # no LLM configured
    ]

    breakdown = reply_breakdown(outcomes)

    assert breakdown.threshold_refusals == 1
    assert breakdown.llm_called == 5
    assert breakdown.cited_answers == 2
    assert breakdown.llm_refusals == 1
    assert breakdown.fallbacks == {"llm_no_valid_citation": 1, "llm_timeout": 1}
    assert breakdown.quoted_without_llm == 1
    assert breakdown.cited_answer_rate == Rate(2, 5)


def test_expected_source_cited_rate_counts_answerable_questions_in_one_mode() -> None:
    outcomes = [
        answered("llm", cited=(ANNUAL,)),
        answered("llm", cited=(SICK, ANNUAL)),
        answered("llm", cited=(SICK,)),
        answered("extractive", cited=(SICK,), generation_ms=None),
        answered("llm", expected=(), cited=(SICK,)),  # unanswerable: not counted
    ]

    assert expected_source_cited_rate(outcomes, "llm") == Rate(2, 3)
    assert expected_source_cited_rate(outcomes, "extractive") == Rate(0, 1)


def test_count_refusals_from_answers_uses_the_mode() -> None:
    outcomes = [
        answered("llm"),
        answered("refused", cited=()),
        answered("llm", expected=()),
        answered("refused", expected=(), cited=()),
    ]

    counts = count_refusals((o.answerable, o.refused) for o in outcomes)

    assert counts == RefusalCounts(answered=1, false_refusals=1, refused=1, false_answers=1)


# --- Error analysis -----------------------------------------------------------------


def test_retrieval_problems_name_a_look_alike_section_in_another_policy() -> None:
    outcome = search(expected=(SICK,), retrieved=(OUTPATIENT, ANNUAL, SICK))

    assert retrieval_problems(outcome, threshold=0.65) == [
        "expected section ranked 3; ranked first: a look-alike section in another policy"
    ]


def test_retrieval_problems_name_another_section_of_the_same_policy() -> None:
    outcome = search(expected=(CARRY,), retrieved=(ANNUAL, SICK))

    assert retrieval_problems(outcome, threshold=0.65) == [
        "expected section not retrieved; ranked first: another section of the same policy"
    ]


def test_retrieval_problems_report_refusal_mistakes_at_the_threshold() -> None:
    falsely_refused = search(expected=(ANNUAL,), retrieved=(ANNUAL,), similarities=(0.612,))
    falsely_answered = search(expected=(), retrieved=(MILEAGE,), similarities=(0.70,))

    assert retrieval_problems(falsely_refused, threshold=0.65) == [
        "refused: best similarity 0.612 is below the threshold 0.65"
    ]
    assert retrieval_problems(falsely_answered, threshold=0.65) == [
        "answered: best similarity 0.700 reaches the threshold 0.65"
    ]


def test_a_question_found_first_and_answered_has_no_retrieval_problem() -> None:
    assert retrieval_problems(search(expected=(ANNUAL,), retrieved=(ANNUAL,)), 0.65) == []
    unanswerable = search(expected=(), retrieved=(SICK,), similarities=(0.5,))
    assert retrieval_problems(unanswerable, 0.65) == []


def test_answer_problems_cover_refusals_fallbacks_and_wrong_citations() -> None:
    assert answer_problems(answered("llm")) == []
    threshold_refusal = answered("refused", cited=(), generation_ms=None, top_similarity=0.612)
    assert answer_problems(threshold_refusal) == [
        "refused before the LLM was asked (best similarity 0.612)"
    ]
    assert answer_problems(answered("refused", cited=())) == ["the LLM refused"]
    assert answer_problems(answered("llm", cited=(SICK,))) == [
        "no expected section cited; cited: leave-policy — 6. Medical Leave"
    ]
    assert answer_problems(answered("extractive", fallback_reason="llm_timeout")) == [
        "fell back to quoting the policy (llm_timeout)"
    ]
    assert answer_problems(answered("llm", expected=(), cited=(SICK,))) == [
        "answered (llm) instead of refusing"
    ]
    assert answer_problems(answered("refused", expected=(), cited=())) == []


# --- Query instruction on or off (decided on the dev set only) ----------------------


@pytest.mark.parametrize(
    ("on", "off", "verdict"),
    [
        ((1.0, 0.90), (1.0, 0.90), "keep-on"),  # a tie keeps the current setting
        ((1.0, 0.95), (1.0, 0.90), "keep-on"),
        ((11 / 12, 0.90), (1.0, 0.90), "off-better"),
        ((1.0, 0.90), (1.0, 0.95), "off-better"),
        ((1.0, 0.90), (11 / 12, 0.95), "mixed"),
    ],
)
def test_instruction_verdict_changes_nothing_without_evidence(
    on: tuple[float, float], off: tuple[float, float], verdict: str
) -> None:
    # (section hit@5, best balanced accuracy) for each setting
    assert instruction_verdict(on=on, off=off) == verdict
