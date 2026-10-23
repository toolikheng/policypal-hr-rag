"""Evaluation reports: Markdown for people to read, JSON with every question's details.

Every report starts with the settings it was made with (REQUIRED_CONFIG_FIELDS), so a
number can always be traced back to how it was measured.
"""

import json
import os
import platform
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from evaluation.datasets import EvalQuestion, QuestionSet
from evaluation.metrics import (
    ANSWERABLE_TYPES,
    UNANSWERABLE_TYPES,
    AnswerOutcome,
    AnswerRun,
    Latency,
    Rate,
    RefusalCounts,
    RetrievalOutcome,
    RetrievalRun,
    SweepRow,
    Verdict,
    all_found_rate,
    answer_problems,
    count_refusals,
    expected_source_cited_rate,
    group_by_type,
    hit_rate,
    refusals_at,
    reply_breakdown,
    retrieval_problems,
    section_rank,
    summarize_latency,
)

REQUIRED_CONFIG_FIELDS = (
    "Date (UTC)",
    "Commit",
    "Question set",
    "Policies",
    "Embedding model",
    "Query instruction",
    "Top k",
    "Threshold",
    "LLM",
    "CPU",
    "RAM",
    "Operating system",
    "Python",
    "Docker",
)

HIT_RANKS = (1, 3, 5)
HIT_LEVELS: tuple[Literal["section", "document"], ...] = ("section", "document")

VERDICT_TEXT: dict[Verdict, str] = {
    "keep-on": "Keep the query instruction on: turning it off is not better on the dev set.",
    "off-better": (
        "Turning the query instruction off is better on the dev set. The app was not"
        " changed: ask the owner before changing the app."
    ),
    "mixed": (
        "Mixed: turning the query instruction off is better on one measure and worse on the"
        " other. The app was not changed; the owner decides."
    ),
}

LIMITATIONS = """\
- The question sets are small, so one question moves a rate by several percentage points.
- The questions were written by the person who built the system, who knows the policies.
  They were committed before any run, and the held-out Training policy is tested separately.
- The policies and questions are fictional sample data in English."""


# --- The three reports --------------------------------------------------------------


def calibration_report(
    config: Mapping[str, str],
    runs: Mapping[str, RetrievalRun],
    sweeps: Mapping[str, Sequence[SweepRow]],
    verdict: Verdict,
) -> str:
    """The dev-set report: the threshold chosen for each instruction setting, and whether
    the dev set favours turning the instruction off. `runs` and `sweeps` are keyed by
    "on" and "off"."""
    settings = list(runs)
    header = ("", *(f"Instruction {setting}" for setting in settings))
    summary = [
        ("Chosen threshold", *(_threshold(runs[s].threshold) for s in settings)),
        *_refusal_rows([refusals_at(runs[s].outcomes, runs[s].threshold) for s in settings]),
        ("Lowest best similarity, answerable", *(_extreme(runs[s], True) for s in settings)),
        ("Highest best similarity, should refuse", *(_extreme(runs[s], False) for s in settings)),
        *_hit_rows([runs[s] for s in settings]),
    ]
    parts = [
        "# Threshold calibration: dev set",
        "Search only (no LLM). For each query-instruction setting, every threshold from 0.50"
        " to 0.85 is tried on the dev set's best-match similarities; the threshold with the"
        " best balanced accuracy is chosen (the middle of a tied range). These numbers choose"
        " settings; they are not the system's reported quality (see the golden-set reports).",
        "## Configuration",
        _config_table(config),
        "## Chosen thresholds",
        _table(header, summary),
        "## Query instruction (decided on the dev set only)",
        VERDICT_TEXT[verdict],
    ]
    for setting in settings:
        parts += [f"## Sweep: instruction {setting}", _sweep_table(sweeps[setting])]
    parts += ["## Each question", _similarity_table(runs, settings)]
    return _join(parts)


def retrieval_report(
    config: Mapping[str, str], runs: Sequence[RetrievalRun], questions: QuestionSet
) -> str:
    """The golden-set search report: the runs side by side, by question type, and every
    mistake explained."""
    labels = [run.label for run in runs]
    results = [
        *_hit_rows(runs),
        (
            "Both sections in the top 5 (two-section questions)",
            *(all_found_rate(_of_type(run.outcomes, "two-section"), 5) for run in runs),
        ),
        ("Threshold", *(_threshold(run.threshold) for run in runs)),
        *_refusal_rows([refusals_at(run.outcomes, run.threshold) for run in runs]),
        (
            "Search time per question (median / mean)",
            *(_latency(summarize_latency([o.retrieval_ms for o in run.outcomes])) for run in runs),
        ),
    ]
    parts = [
        f"# Retrieval evaluation: {questions.name} set",
        "Search only (no LLM). Hit rate@k: the share of answerable questions with an expected"
        " section in the top k results. Refusals: a question is refused when its best match is"
        " below the threshold, as in the app.",
        "## Configuration",
        _config_table(config),
        "## Results",
        _table(("", *labels), results),
    ]
    for k in (1, 5):
        parts += [f"## Section hit@{k} by question type", _by_type_table(runs, k)]
    parts += [
        "## Refusals by question type (should be refused)",
        _table(
            ("Question type", *labels),
            [
                (
                    f"{kind} ({len(_of_type(runs[0].outcomes, kind))})",
                    *(_refused_rate(run, kind) for run in runs),
                )
                for kind in UNANSWERABLE_TYPES
                if _of_type(runs[0].outcomes, kind)
            ],
        ),
        "## Error analysis",
        "Every question that was not perfect: the expected section was not ranked first, an"
        " answerable question would be refused, or a question that should be refused would be"
        " answered. The reason combines what happened with the note written with the question.",
    ]
    by_id = _by_id(questions)
    for run in runs:
        rows = [
            (
                o.question_id,
                o.question_type,
                by_id[o.question_id].question,
                _sections(o.expected),
                "; ".join(f"{m.section} ({m.similarity:.3f})" for m in o.retrieved[:3]),
                _reason(problems, by_id[o.question_id]),
            )
            for o in run.outcomes
            if (problems := retrieval_problems(o, run.threshold))
        ]
        header = ("ID", "Type", "Question", "Expected", "Retrieved (top 3)", "Reason")
        parts += [f"### {run.label}", _table(header, rows) if rows else "No mistakes."]
    parts += ["## Limitations", LIMITATIONS]
    return _join(parts)


def end_to_end_report(config: Mapping[str, str], run: AnswerRun, questions: QuestionSet) -> str:
    """The golden-set report for the full pipeline: refusals, how each reply was made,
    citations, latency, and every wrong answer."""
    outcomes = run.outcomes
    breakdown = reply_breakdown(outcomes)
    results = [
        *_refusal_rows([count_refusals((o.answerable, o.refused) for o in outcomes)]),
        ("Refused before the LLM was asked", breakdown.threshold_refusals),
        ("Questions the LLM was asked", breakdown.llm_called),
        ("Answers with a valid citation", breakdown.cited_answer_rate),
        ("Refused by the LLM", breakdown.llm_refusals),
        *((f"Fell back to quoting: {r}", n) for r, n in sorted(breakdown.fallbacks.items())),
        ("Quoted without an LLM (extractive mode)", breakdown.quoted_without_llm),
        ("Expected section cited (LLM answers)", expected_source_cited_rate(outcomes, "llm")),
        (
            "Expected section cited (quoted answers)",
            expected_source_cited_rate(outcomes, "extractive"),
        ),
        ("Warm-up answer (not counted below)", _duration(run.warm_up_ms)),
    ]
    modes = sorted({o.mode for o in outcomes})
    latency_rows = [
        (mode, *_latency_cells(summarize_latency([o.total_ms for o in outcomes if o.mode == mode])))
        for mode in modes
    ]
    generation = summarize_latency(
        [o.generation_ms for o in outcomes if o.generation_ms is not None]
    )
    if generation:
        latency_rows.append(("LLM generation only", *_latency_cells(generation)))
    by_id = _by_id(questions)
    rows = [
        (
            o.question_id,
            o.question_type,
            by_id[o.question_id].question,
            _sections(o.expected),
            f"[{o.mode}] {_shorten(o.answer)}",
            _reason(problems, by_id[o.question_id]),
        )
        for o in outcomes
        if (problems := answer_problems(o))
    ]
    parts = [
        f"# End-to-end evaluation: {questions.name} set, {run.provider}",
        "The full pipeline, as `/ask` runs it (search, threshold, LLM, citation checks),"
        " without saving answers. A refusal is the mode `refused`; an extractive fallback"
        " counts as an answer.",
        "## Configuration",
        _config_table(config),
        "## Results",
        _table(("", "Value"), results),
        "## Answer time by mode",
        _table(("Mode", "Questions", "Median", "Mean", "Max"), latency_rows),
        "## By question type",
        _answers_by_type_table(outcomes),
        "## Error analysis",
        "Every question with a wrong refusal, a fallback, a missing expected citation, or an"
        " answer where a refusal was expected.",
        (
            _table(("ID", "Type", "Question", "Expected", "Answer", "Reason"), rows)
            if rows
            else "No mistakes."
        ),
        "## Not measured",
        "Whether the answer text is correct and complete is not checked automatically: that"
        " needs a person or an LLM judge. The error analysis shows each answer that went wrong"
        " so it can be read. A missing-detail question counts as answered when the model"
        " explains the gap instead of using the refusal sentence.",
        "## Limitations",
        LIMITATIONS,
    ]
    return _join(parts)


# --- Files and environment ----------------------------------------------------------


def write_report(
    results_dir: Path, name: str, markdown: str, data: Mapping[str, Any]
) -> tuple[Path, Path]:
    """Save `<name>.md` and `<name>.json` in `results_dir`."""
    results_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = results_dir / f"{name}.md"
    json_path = results_dir / f"{name}.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return markdown_path, json_path


def environment() -> dict[str, str]:
    """The machine the evaluation ran on. Inside Docker, CPU and memory are the Docker VM's.
    The Docker version is only visible on the host, so the Makefile passes it in."""
    return {
        "CPU": f"{_cpu_model()} ({os.cpu_count()} logical CPUs)",
        "RAM": _memory(),
        "Operating system": platform.platform(),
        "Python": platform.python_version(),
        "Docker": os.environ.get("EVAL_DOCKER_VERSION") or "not recorded (EVAL_DOCKER_VERSION)",
    }


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _memory() -> str:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return f"{int(line.split()[1]) / 1024**2:.1f} GiB visible"
    except OSError:
        pass
    return "unknown"


# --- Tables -----------------------------------------------------------------------------


def _config_table(config: Mapping[str, str]) -> str:
    missing = [field for field in REQUIRED_CONFIG_FIELDS if field not in config]
    if missing:
        raise ValueError(f"the report is missing configuration fields: {', '.join(missing)}")
    return _table(
        ("Setting", "Value"), [(field, config[field]) for field in REQUIRED_CONFIG_FIELDS]
    )


def _hit_rows(runs: Sequence[RetrievalRun]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for level in HIT_LEVELS:
        for k in HIT_RANKS:
            rates = (hit_rate(run.outcomes, k, level=level) for run in runs)
            rows.append((f"{level.capitalize()} hit@{k}", *rates))
    return rows


def _refusal_rows(counts: Sequence[RefusalCounts]) -> list[tuple[object, ...]]:
    return [
        ("Refusal accuracy", *(_percent(c.accuracy) for c in counts)),
        ("Balanced accuracy", *(_percent(c.balanced_accuracy) for c in counts)),
        (
            "Answerable questions answered",
            *(Rate(c.answered, c.answered + c.false_refusals) for c in counts),
        ),
        (
            "Should-refuse questions refused",
            *(Rate(c.refused, c.refused + c.false_answers) for c in counts),
        ),
    ]


def _by_type_table(runs: Sequence[RetrievalRun], k: int) -> str:
    groups = [group_by_type(run.outcomes) for run in runs]
    rows = [
        (f"{kind} ({len(outcomes)})", *(hit_rate(g[kind], k) for g in groups))
        for kind, outcomes in groups[0].items()
    ]
    return _table(("Question type", *(run.label for run in runs)), rows)


def _answers_by_type_table(outcomes: Sequence[AnswerOutcome]) -> str:
    rows = []
    for kind in (*ANSWERABLE_TYPES, *UNANSWERABLE_TYPES):
        group = [o for o in outcomes if o.question_type == kind]
        if not group:
            continue
        if group[0].answerable:
            answered = Rate(sum(not o.refused for o in group), len(group))
            clean = Rate(sum(not answer_problems(o) for o in group), len(group))
            rows.append((f"{kind} ({len(group)})", answered, clean, ""))
        else:
            rows.append(
                (f"{kind} ({len(group)})", "", "", Rate(sum(o.refused for o in group), len(group)))
            )
    header = ("Question type", "Answered", "Expected section cited, no fallback", "Refused")
    return _table(header, rows)


def _sweep_table(rows: Sequence[SweepRow]) -> str:
    header = (
        "Threshold",
        "Answerable answered",
        "False refusals",
        "Should-refuse refused",
        "False answers",
        "Balanced accuracy",
    )
    return _table(
        header,
        [
            (
                _threshold(row.threshold),
                row.counts.answered,
                row.counts.false_refusals,
                row.counts.refused,
                row.counts.false_answers,
                _percent(row.counts.balanced_accuracy),
            )
            for row in rows
        ],
    )


def _similarity_table(runs: Mapping[str, RetrievalRun], settings: Sequence[str]) -> str:
    header = (
        "ID",
        "Type",
        *(f"Best similarity ({s})" for s in settings),
        *(f"Expected section rank ({s})" for s in settings),
    )
    first = runs[settings[0]].outcomes
    rows = [
        (
            outcome.question_id,
            outcome.question_type,
            *(_score(runs[s].outcomes[index].top_similarity) for s in settings),
            *(_rank(runs[s].outcomes[index]) for s in settings),
        )
        for index, outcome in enumerate(first)
    ]
    return _table(header, rows)


def _table(header: Sequence[object], rows: Iterable[Sequence[object]]) -> str:
    lines = [_row(header), "|" + "---|" * len(header)]
    lines += [_row(row) for row in rows]
    return "\n".join(lines)


def _row(cells: Sequence[object]) -> str:
    texts = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells]
    return "|" + "|".join(f" {text} " if text else " " for text in texts) + "|"


# --- Small helpers --------------------------------------------------------------------


def _refused_rate(run: RetrievalRun, kind: str) -> Rate:
    """Of the should-refuse questions of this type, how many the threshold refuses."""
    group = _of_type(run.outcomes, kind)
    return Rate(refusals_at(group, run.threshold).refused, len(group))


def _extreme(run: RetrievalRun, answerable: bool) -> str:
    scores = [o.top_similarity or 0.0 for o in run.outcomes if o.answerable == answerable]
    if not scores:
        return "n/a"
    return _score(min(scores) if answerable else max(scores))


def _of_type(outcomes: Sequence[RetrievalOutcome], kind: str) -> list[RetrievalOutcome]:
    return [o for o in outcomes if o.question_type == kind]


def _by_id(questions: QuestionSet) -> dict[str, EvalQuestion]:
    return {question.id: question for question in questions.questions}


def _reason(problems: Sequence[str], question: EvalQuestion) -> str:
    return "; ".join(problems) + f". Note: {question.note}"


def _sections(sections: Sequence[object]) -> str:
    return "; ".join(str(section) for section in sections) or "(should be refused)"


def _rank(outcome: RetrievalOutcome) -> str:
    if not outcome.answerable:
        return "-"
    rank = section_rank(outcome)
    return "not found" if rank is None else str(rank)


def _shorten(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _threshold(value: float) -> str:
    return f"{value:g}"


def _score(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _duration(ms: float | None) -> str:
    if ms is None:
        return "n/a"
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def _latency(latency: Latency | None) -> str:
    if latency is None:
        return "n/a"
    return f"{_duration(latency.median_ms)} / {_duration(latency.mean_ms)}"


def _latency_cells(latency: Latency | None) -> tuple[object, ...]:
    if latency is None:
        return (0, "n/a", "n/a", "n/a")
    return (
        latency.count,
        _duration(latency.median_ms),
        _duration(latency.mean_ms),
        _duration(latency.max_ms),
    )


def _join(parts: Sequence[str]) -> str:
    return "\n\n".join(parts) + "\n"
