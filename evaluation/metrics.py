"""Evaluation metrics: pure functions on plain data, so each one can be checked by hand.

Retrieval (search only, no LLM):
- hit rate@k: the share of answerable questions with an expected section in the top k results
- refusals at a threshold: the app refuses when the best similarity is below it

End to end (the full pipeline):
- refusals from the answer's mode, how each reply was produced, expected-source-cited rate

Both: latency (mean, median, max) and the problems listed in a report's error analysis.
"""

import math
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

# Each question has one type: the main thing that makes it hard. Report order.
ANSWERABLE_TYPES = ("plain", "look-alike", "table", "amendment", "two-section")
UNANSWERABLE_TYPES = ("uncovered-topic", "missing-detail")

# The thresholds the calibration sweep tries: 0.50, 0.51, ..., 0.85.
THRESHOLD_GRID = tuple(round(0.50 + step / 100, 2) for step in range(36))


@dataclass(frozen=True)
class Section:
    """A place in a policy: the document's slug and the section heading as written."""

    document: str
    section: str

    def __str__(self) -> str:
        return f"{self.document} — {self.section}"


@dataclass(frozen=True)
class Match:
    """One search result: the chunk's section and its similarity to the question."""

    section: Section
    similarity: float


@dataclass(frozen=True)
class Rate:
    """A count out of a total, e.g. 37 of 40 questions."""

    hits: int
    total: int

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    def __str__(self) -> str:
        return f"{self.hits}/{self.total} ({self.value:.1%})" if self.total else "n/a"


@dataclass(frozen=True)
class RetrievalOutcome:
    """One question's search results."""

    question_id: str
    question_type: str
    expected: tuple[Section, ...]  # empty: the question should be refused
    retrieved: tuple[Match, ...]  # best first
    retrieval_ms: int

    @property
    def answerable(self) -> bool:
        return bool(self.expected)

    @property
    def top_similarity(self) -> float | None:
        return self.retrieved[0].similarity if self.retrieved else None


@dataclass(frozen=True)
class AnswerOutcome:
    """One question's answer from the full pipeline."""

    question_id: str
    question_type: str
    expected: tuple[Section, ...]  # empty: the question should be refused
    mode: str  # llm, extractive or refused
    answer: str
    cited: tuple[Section, ...]
    fallback_reason: str | None
    retrieved: tuple[Match, ...]  # best first
    retrieval_ms: int
    generation_ms: int | None  # None: the LLM was not asked
    total_ms: int

    @property
    def answerable(self) -> bool:
        return bool(self.expected)

    @property
    def refused(self) -> bool:
        return self.mode == "refused"

    @property
    def llm_called(self) -> bool:
        return self.generation_ms is not None

    @property
    def top_similarity(self) -> float | None:
        return self.retrieved[0].similarity if self.retrieved else None


# --- Retrieval: ranks and hit rates -------------------------------------------------


def section_rank(outcome: RetrievalOutcome) -> int | None:
    """Rank (1 = best) of the first result from an expected section; None if none."""
    expected = set(outcome.expected)
    return _first_rank(match.section in expected for match in outcome.retrieved)


def document_rank(outcome: RetrievalOutcome) -> int | None:
    """Rank of the first result from an expected policy, whatever its section."""
    expected = {section.document for section in outcome.expected}
    return _first_rank(match.section.document in expected for match in outcome.retrieved)


def hit_rate(
    outcomes: Iterable[RetrievalOutcome],
    k: int,
    *,
    level: Literal["section", "document"] = "section",
) -> Rate:
    """How many answerable questions have an expected section (or policy) in the top k."""
    rank_of = section_rank if level == "section" else document_rank
    answerable = [outcome for outcome in outcomes if outcome.answerable]
    return Rate(sum(_within(rank_of(outcome), k) for outcome in answerable), len(answerable))


def all_found_rate(outcomes: Iterable[RetrievalOutcome], k: int) -> Rate:
    """How many answerable questions have every expected section in the top k (for
    questions that need two sections)."""
    answerable = [outcome for outcome in outcomes if outcome.answerable]
    found = sum(
        set(outcome.expected) <= {match.section for match in outcome.retrieved[:k]}
        for outcome in answerable
    )
    return Rate(found, len(answerable))


def group_by_type(outcomes: Iterable[RetrievalOutcome]) -> dict[str, list[RetrievalOutcome]]:
    """The answerable questions grouped by type, in report order (empty types left out)."""
    groups: dict[str, list[RetrievalOutcome]] = {name: [] for name in ANSWERABLE_TYPES}
    for outcome in outcomes:
        if outcome.answerable:
            groups[outcome.question_type].append(outcome)
    return {name: group for name, group in groups.items() if group}


# --- Refusals and the threshold sweep -----------------------------------------------


def refused_at(top_similarity: float | None, threshold: float) -> bool:
    """The app's rule: refuse when nothing was found or the best match is below the
    threshold (a match exactly at the threshold is used)."""
    return top_similarity is None or top_similarity < threshold


@dataclass(frozen=True)
class RefusalCounts:
    answered: int  # answerable questions that were answered (right)
    false_refusals: int  # answerable questions that were refused (wrong)
    refused: int  # unanswerable questions that were refused (right)
    false_answers: int  # unanswerable questions that were answered (wrong)

    @property
    def total(self) -> int:
        return self.answered + self.false_refusals + self.refused + self.false_answers

    @property
    def accuracy(self) -> float | None:
        return (self.answered + self.refused) / self.total if self.total else None

    @property
    def balanced_accuracy(self) -> float | None:
        """The mean of "answerable questions answered" and "unanswerable questions refused",
        so the bigger group can't hide mistakes in the smaller one."""
        rates = [
            Rate(self.answered, self.answered + self.false_refusals).value,
            Rate(self.refused, self.refused + self.false_answers).value,
        ]
        present = [rate for rate in rates if rate is not None]
        return sum(present) / len(present) if present else None


def count_refusals(cases: Iterable[tuple[bool, bool]]) -> RefusalCounts:
    """`cases` holds (answerable, refused) for each question."""
    counts = Counter(cases)
    return RefusalCounts(
        answered=counts[(True, False)],
        false_refusals=counts[(True, True)],
        refused=counts[(False, True)],
        false_answers=counts[(False, False)],
    )


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    counts: RefusalCounts


def sweep(
    outcomes: Sequence[RetrievalOutcome], thresholds: Sequence[float] = THRESHOLD_GRID
) -> list[SweepRow]:
    """Refusal counts at each threshold. Nothing is searched again: the same best
    similarities are compared with each threshold."""
    return [
        SweepRow(
            threshold,
            count_refusals(
                (outcome.answerable, refused_at(outcome.top_similarity, threshold))
                for outcome in outcomes
            ),
        )
        for threshold in thresholds
    ]


def choose_threshold(rows: Sequence[SweepRow]) -> float:
    """The threshold with the best balanced accuracy. `rows` must be in ascending order.

    When neighbouring thresholds tie, the middle of the run is taken, as far as possible
    from mistakes on either side. If separate runs tie, the longest wins, then the lowest
    (a lower threshold refuses less, and the LLM can still refuse).
    """
    scores = [row.counts.balanced_accuracy or 0.0 for row in rows]
    best = max(scores)
    runs: list[list[float]] = []
    previous_was_best = False
    for row, score in zip(rows, scores, strict=True):
        is_best = math.isclose(score, best)
        if is_best and previous_was_best:
            runs[-1].append(row.threshold)
        elif is_best:
            runs.append([row.threshold])
        previous_was_best = is_best
    longest = max(runs, key=len)  # the first (lowest) of equally long runs
    return round((longest[0] + longest[-1]) / 2, 3)


# --- Latency ------------------------------------------------------------------------


@dataclass(frozen=True)
class Latency:
    count: int
    mean_ms: float
    median_ms: float
    max_ms: int


def summarize_latency(values: Sequence[int]) -> Latency | None:
    """Mean, median and maximum. The median shows a typical wait; one slow cold start
    pulls the mean up."""
    if not values:
        return None
    return Latency(len(values), statistics.mean(values), statistics.median(values), max(values))


# --- End to end ---------------------------------------------------------------------


@dataclass(frozen=True)
class ReplyBreakdown:
    threshold_refusals: int  # refused before the LLM was asked
    llm_called: int
    cited_answers: int  # the LLM answered with a valid citation
    llm_refusals: int  # the LLM said the excerpts don't answer the question
    fallbacks: dict[str, int]  # the LLM was asked, then the policy was quoted; by reason
    quoted_without_llm: int  # no LLM configured: the policy was quoted

    @property
    def cited_answer_rate(self) -> Rate:
        """Of the questions the LLM was asked, how many got a cited answer."""
        return Rate(self.cited_answers, self.llm_called)


def reply_breakdown(outcomes: Iterable[AnswerOutcome]) -> ReplyBreakdown:
    outcomes = list(outcomes)
    asked = [outcome for outcome in outcomes if outcome.llm_called]
    return ReplyBreakdown(
        threshold_refusals=sum(o.refused and not o.llm_called for o in outcomes),
        llm_called=len(asked),
        cited_answers=sum(o.mode == "llm" for o in asked),
        llm_refusals=sum(o.refused for o in asked),
        fallbacks=dict(
            Counter(o.fallback_reason or "none" for o in asked if o.mode == "extractive")
        ),
        quoted_without_llm=sum(o.mode == "extractive" and not o.llm_called for o in outcomes),
    )


def expected_source_cited_rate(outcomes: Iterable[AnswerOutcome], mode: str) -> Rate:
    """Of the answerable questions answered in `mode`, how many cite an expected section."""
    answers = [o for o in outcomes if o.answerable and o.mode == mode]
    return Rate(sum(_cites_expected(o) for o in answers), len(answers))


# --- Error analysis -----------------------------------------------------------------


def retrieval_problems(outcome: RetrievalOutcome, threshold: float) -> list[str]:
    """What went wrong for one question in a retrieval run; empty if nothing did.

    For an answerable question: the expected section wasn't ranked first, or the question
    would be refused. For an unanswerable one: it would be answered.
    """
    problems = []
    top = outcome.top_similarity
    if outcome.answerable:
        rank = section_rank(outcome)
        if rank != 1:
            found = "not retrieved" if rank is None else f"ranked {rank}"
            problems.append(f"expected section {found}; ranked first: {_first_result(outcome)}")
        if refused_at(top, threshold):
            problems.append(
                f"refused: best similarity {_score(top)} is below the threshold {threshold}"
            )
    elif not refused_at(top, threshold):
        problems.append(
            f"answered: best similarity {_score(top)} reaches the threshold {threshold}"
        )
    return problems


def answer_problems(outcome: AnswerOutcome) -> list[str]:
    """What went wrong for one question in an end-to-end run; empty if nothing did."""
    if not outcome.answerable:
        return [] if outcome.refused else [f"answered ({outcome.mode}) instead of refusing"]
    if outcome.refused and not outcome.llm_called:
        return [
            f"refused before the LLM was asked (best similarity {_score(outcome.top_similarity)})"
        ]
    if outcome.refused:
        return ["the LLM refused"]
    problems = []
    if outcome.fallback_reason:
        problems.append(f"fell back to quoting the policy ({outcome.fallback_reason})")
    if not _cites_expected(outcome):
        cited = "; ".join(str(section) for section in outcome.cited) or "nothing"
        problems.append(f"no expected section cited; cited: {cited}")
    return problems


def _first_result(outcome: RetrievalOutcome) -> str:
    if not outcome.retrieved:
        return "nothing"
    expected_documents = {section.document for section in outcome.expected}
    if outcome.retrieved[0].section.document in expected_documents:
        return "another section of the same policy"
    return "a look-alike section in another policy"


def _cites_expected(outcome: AnswerOutcome) -> bool:
    return not set(outcome.cited).isdisjoint(outcome.expected)


def _first_rank(flags: Iterable[bool]) -> int | None:
    return next((rank for rank, flag in enumerate(flags, start=1) if flag), None)


def _within(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def _score(similarity: float | None) -> str:
    return "none" if similarity is None else f"{similarity:.3f}"
