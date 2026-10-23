"""Evaluation reports, built from small hand-made results (no database, no model)."""

import json
from pathlib import Path

import pytest

from evaluation.datasets import EvalQuestion, QuestionSet
from evaluation.metrics import AnswerOutcome, Match, RetrievalOutcome, Section, sweep
from evaluation.report import (
    REQUIRED_CONFIG_FIELDS,
    AnswerRun,
    RetrievalRun,
    calibration_report,
    end_to_end_report,
    environment,
    retrieval_report,
    write_report,
)

SICK = Section("leave-policy", "5.1 Sick Leave (Outpatient)")
MC = Section("medical-claims-policy", "3.4 Medical Certificates")
FINES = Section("expense-claims-policy", "7. Items That Cannot Be Claimed")

QUESTIONS = QuestionSet(
    name="sample",
    questions=(
        EvalQuestion(
            "q1", "When do I upload my MC?", "look-alike", (SICK,), "Medical 3.4 is close."
        ),
        EvalQuestion("q2", "Can I claim a parking fine?", "plain", (FINES,), "Fines are excluded."),
        EvalQuestion("q3", "Is there a bonus?", "uncovered-topic", (), "Reserved topic."),
    ),
)

CONFIG = {field: f"<{field} value>" for field in REQUIRED_CONFIG_FIELDS}


def search(qid: str, *matches: tuple[Section, float]) -> RetrievalOutcome:
    question = next(q for q in QUESTIONS.questions if q.id == qid)
    return RetrievalOutcome(
        question_id=qid,
        question_type=question.type,
        expected=question.expected,
        retrieved=tuple(Match(section, similarity) for section, similarity in matches),
        retrieval_ms=40,
    )


def answer(
    qid: str, mode: str, *, cited: tuple[Section, ...] = (), **fields: object
) -> AnswerOutcome:
    question = next(q for q in QUESTIONS.questions if q.id == qid)
    values: dict = {
        "answer": "Upload it within 48 hours [1].",
        "fallback_reason": None,
        "retrieved": (Match(SICK, 0.8),),
        "retrieval_ms": 40,
        "generation_ms": 9000,
        "total_ms": 9100,
    }
    values.update(fields)
    return AnswerOutcome(
        question_id=qid,
        question_type=question.type,
        expected=question.expected,
        mode=mode,
        cited=cited,
        **values,
    )


# A look-alike miss (q1), a hit (q2) and a correct refusal (q3), at threshold 0.65.
MD_RUN = RetrievalRun(
    source="md",
    instruction=True,
    threshold=0.65,
    outcomes=(
        search("q1", (MC, 0.75), (SICK, 0.72)),
        search("q2", (FINES, 0.81)),
        search("q3", (MC, 0.55)),
    ),
)
# Everything right.
PDF_RUN = RetrievalRun(
    source="pdf",
    instruction=True,
    threshold=0.65,
    outcomes=(
        search("q1", (SICK, 0.76), (MC, 0.74)),
        search("q2", (FINES, 0.80)),
        search("q3", (MC, 0.50)),
    ),
)


def test_run_labels_name_the_source_and_the_instruction() -> None:
    assert MD_RUN.label == "Markdown, instruction on"
    assert RetrievalRun("pdf", False, 0.6, ()).label == "PDF, instruction off"


# --- Configuration --------------------------------------------------------------------


def all_reports() -> dict[str, str]:
    e2e = AnswerRun("ollama", "llama3.2:3b", 0.65, (answer("q1", "llm", cited=(SICK,)),), 30000)
    sweeps = {"on": sweep(MD_RUN.outcomes, (0.6, 0.7))}
    return {
        "retrieval": retrieval_report(CONFIG, [MD_RUN, PDF_RUN], QUESTIONS),
        "end-to-end": end_to_end_report(CONFIG, e2e, QUESTIONS),
        "calibration": calibration_report(CONFIG, {"on": MD_RUN}, sweeps, "keep-on"),
    }


@pytest.mark.parametrize("report", ["retrieval", "end-to-end", "calibration"])
def test_every_report_lists_every_configuration_field(report: str) -> None:
    markdown = all_reports()[report]

    for field in REQUIRED_CONFIG_FIELDS:
        assert f"| {field} | <{field} value> |" in markdown


def test_the_configuration_names_what_the_plan_requires() -> None:
    for field in (
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
        "Docker",
    ):
        assert field in REQUIRED_CONFIG_FIELDS


def test_a_report_with_a_missing_configuration_field_is_refused() -> None:
    config = {field: value for field, value in CONFIG.items() if field != "CPU"}

    with pytest.raises(ValueError, match="CPU"):
        retrieval_report(config, [MD_RUN], QUESTIONS)


# --- Retrieval report -----------------------------------------------------------------


def test_retrieval_report_shows_the_runs_side_by_side() -> None:
    markdown = retrieval_report(CONFIG, [MD_RUN, PDF_RUN], QUESTIONS)

    assert "| | Markdown, instruction on | PDF, instruction on |" in markdown
    assert "| Section hit@1 | 1/2 (50.0%) | 2/2 (100.0%) |" in markdown
    assert "| Section hit@3 | 2/2 (100.0%) | 2/2 (100.0%) |" in markdown
    assert "| Threshold | 0.65 | 0.65 |" in markdown
    assert "| Refusal accuracy | 100.0% | 100.0% |" in markdown


def test_retrieval_report_breaks_hit_rate_down_by_question_type() -> None:
    markdown = retrieval_report(CONFIG, [MD_RUN, PDF_RUN], QUESTIONS)

    assert "| plain (1) | 1/1 (100.0%) | 1/1 (100.0%) |" in markdown
    assert "| look-alike (1) | 0/1 (0.0%) | 1/1 (100.0%) |" in markdown
    assert "| uncovered-topic (1) | 1/1 (100.0%) | 1/1 (100.0%) |" in markdown


def test_retrieval_error_analysis_lists_each_mistake_with_what_was_found_and_why() -> None:
    markdown = retrieval_report(CONFIG, [MD_RUN, PDF_RUN], QUESTIONS)

    row = next(line for line in markdown.splitlines() if line.startswith("| q1 |"))
    assert "| look-alike |" in row
    assert "When do I upload my MC?" in row
    assert str(SICK) in row  # expected
    assert f"{MC} (0.750)" in row  # retrieved instead
    assert "a look-alike section in another policy" in row  # reason
    assert "Medical 3.4 is close." in row  # the note written with the question
    assert "| q2 |" not in markdown  # found first: not a mistake
    assert "No mistakes." in markdown  # the PDF run


# --- End-to-end report ------------------------------------------------------------------


def test_end_to_end_report_shows_how_replies_were_made_and_lists_wrong_answers() -> None:
    run = AnswerRun(
        provider="ollama",
        model="llama3.2:3b",
        threshold=0.65,
        outcomes=(
            answer("q1", "llm", cited=(MC,), answer="No MC needed [1]."),
            answer("q2", "extractive", cited=(FINES,), fallback_reason="llm_timeout"),
            answer("q3", "refused", generation_ms=None, total_ms=30),
        ),
        warm_up_ms=31000,
    )

    markdown = end_to_end_report(CONFIG, run, QUESTIONS)

    assert "| Refusal accuracy | 100.0% |" in markdown
    assert "| Questions the LLM was asked | 2 |" in markdown
    assert "| Answers with a valid citation | 1/2 (50.0%) |" in markdown
    assert "| Fell back to quoting: llm_timeout | 1 |" in markdown
    assert "| Warm-up answer (not counted below) | 31.0 s |" in markdown
    q1 = next(line for line in markdown.splitlines() if line.startswith("| q1 |"))
    assert "No MC needed [1]." in q1
    assert f"no expected section cited; cited: {MC}" in q1
    q2 = next(line for line in markdown.splitlines() if line.startswith("| q2 |"))
    assert "fell back to quoting the policy (llm_timeout)" in q2
    assert "| q3 |" not in markdown


def test_end_to_end_report_says_what_is_not_measured() -> None:
    run = AnswerRun("extractive", None, 0.65, (answer("q3", "refused", generation_ms=None),), None)

    markdown = end_to_end_report(CONFIG, run, QUESTIONS)

    assert "not checked automatically" in markdown


# --- Calibration report -----------------------------------------------------------------


def test_calibration_report_states_the_chosen_thresholds_and_the_verdict() -> None:
    off = RetrievalRun("md", False, 0.6, MD_RUN.outcomes)
    sweeps = {"on": sweep(MD_RUN.outcomes, (0.6, 0.7)), "off": sweep(off.outcomes, (0.6, 0.7))}

    markdown = calibration_report(CONFIG, {"on": MD_RUN, "off": off}, sweeps, "off-better")

    assert "| Chosen threshold | 0.65 | 0.6 |" in markdown
    assert "ask the owner before changing the app" in markdown
    assert "| 0.6 | 2 | 0 | 1 | 0 | 100.0% |" in markdown  # a sweep row


# --- Files and environment ------------------------------------------------------------


def test_write_report_saves_markdown_and_json(tmp_path: Path) -> None:
    markdown_path, json_path = write_report(tmp_path, "golden-retrieval", "# Report\n", {"a": 1})

    assert markdown_path == tmp_path / "golden-retrieval.md"
    assert markdown_path.read_text(encoding="utf-8") == "# Report\n"
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"a": 1}


def test_environment_describes_the_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_DOCKER_VERSION", "Docker Desktop 4.86.0")

    facts = environment()

    assert set(facts) == {"CPU", "RAM", "Operating system", "Python", "Docker"}
    assert facts["Docker"] == "Docker Desktop 4.86.0"
    assert all(facts.values())
