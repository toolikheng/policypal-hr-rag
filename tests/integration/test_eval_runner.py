"""The evaluation runner on a real PostgreSQL, with the fake embedder and fake LLM."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select, text

from evaluation.datasets import EvalQuestion, QuestionSet
from evaluation.metrics import Section
from evaluation.report import REQUIRED_CONFIG_FIELDS
from evaluation.run_eval import (
    BASE_CONFIG_FIELDS,
    base_config,
    calibrate,
    create_database_if_missing,
    eval_database_url,
    evaluate_end_to_end,
    evaluate_retrieval,
    load_policies,
    load_thresholds,
    run_end_to_end,
    run_retrieval,
)
from policypal.models import Document, DocumentChunk
from tests.fakes import FakeEmbedder, FakeLLM
from tests.helpers import make_settings
from tests.sample_data import CORE_POLICY_SLUGS

CARRY = Section("leave-policy", "4.3 Carry Forward of Annual Leave")
QUESTIONS = QuestionSet(
    name="sample",
    questions=(
        EvalQuestion(
            "s1",
            "How many days of annual leave can I carry forward?",
            "plain",
            (CARRY,),
            "n",
        ),
        EvalQuestion("s2", "Is there a bonus?", "uncovered-topic", (), "n"),
    ),
)


@pytest.fixture
def base() -> dict[str, str]:
    return {field: "x" for field in BASE_CONFIG_FIELDS}


@contextmanager
def loaded(database_url: str, source: str = "md", **kwargs: object) -> Iterator[Engine]:
    engine = load_policies(database_url, FakeEmbedder(), source, **kwargs)  # type: ignore[arg-type]
    try:
        yield engine
    finally:
        engine.dispose()


def documents(engine: Engine) -> list[tuple[str, str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(Document.slug, Document.file_type, Document.origin).order_by(Document.slug)
        )
        return [tuple(row) for row in rows]


def chunk_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM chunks")).scalar_one()


# --- The evaluation database ----------------------------------------------------------


def test_the_evaluation_database_sits_next_to_the_apps_database() -> None:
    url = eval_database_url("postgresql+psycopg://user:secret@db:5432/policypal")

    assert url == "postgresql+psycopg://user:secret@db:5432/policypal_eval"


def test_create_database_if_missing_creates_it_once(test_database_url: str) -> None:
    url = test_database_url.rsplit("/", 1)[0] + "/policypal_eval_check"
    server = create_engine(test_database_url, isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS policypal_eval_check"))

        assert create_database_if_missing(url) is True
        assert create_database_if_missing(url) is False
    finally:
        with server.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS policypal_eval_check"))
        server.dispose()


def test_load_policies_holds_exactly_the_eight_sample_policies(migrated_database_url: str) -> None:
    with loaded(migrated_database_url, "pdf"):
        pass
    with loaded(migrated_database_url, "md") as engine:
        assert documents(engine) == [(slug, "md", "sample") for slug in sorted(CORE_POLICY_SLUGS)]
        assert chunk_count(engine) == 119


def test_load_policies_can_use_the_pdf_versions(migrated_database_url: str) -> None:
    with loaded(migrated_database_url, "pdf") as engine:
        assert documents(engine) == [(slug, "pdf", "sample") for slug in sorted(CORE_POLICY_SLUGS)]
        assert chunk_count(engine) == 119


def test_load_policies_empties_the_question_history(migrated_database_url: str) -> None:
    with loaded(migrated_database_url) as engine:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO conversations (id, channel) VALUES (gen_random_uuid(), 'api')")
            )
    with loaded(migrated_database_url) as engine:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM conversations")).scalar_one() == 0


def test_load_policies_adds_extra_files_as_uploads(
    migrated_database_url: str, tmp_path: Path
) -> None:
    extra = tmp_path / "canteen-policy.md"
    extra.write_text("# Canteen Policy\n\n## 1. Opening Hours\n\nOpen 8 to 5.\n", encoding="utf-8")

    with loaded(migrated_database_url, extra_files=[extra]) as engine:
        assert ("canteen-policy", "md", "upload") in documents(engine)
        assert len(documents(engine)) == 9


# --- Running the questions ------------------------------------------------------------


def test_run_retrieval_reports_each_result_by_policy_slug_and_section(
    migrated_database_url: str,
) -> None:
    with loaded(migrated_database_url) as engine:
        outcomes = run_retrieval(engine, FakeEmbedder(), QUESTIONS, top_k=5)

    first, second = outcomes
    assert first.question_id == "s1"
    assert first.expected == (CARRY,)
    assert len(first.retrieved) == 5
    assert all(match.section.document in CORE_POLICY_SLUGS for match in first.retrieved)
    assert first.retrieved[0].section.document == "leave-policy"
    assert first.retrieval_ms >= 0
    assert second.expected == ()


def test_run_end_to_end_records_the_mode_citations_and_timings(migrated_database_url: str) -> None:
    with loaded(migrated_database_url) as engine:
        embedder = FakeEmbedder()
        llm_answers = run_end_to_end(
            engine, embedder, FakeLLM("Five days [1]."), QUESTIONS, top_k=5, min_similarity=0.0
        )
        quoted = run_end_to_end(engine, embedder, None, QUESTIONS, top_k=5, min_similarity=0.0)
        refused = run_end_to_end(engine, embedder, None, QUESTIONS, top_k=5, min_similarity=0.99)

    answer = llm_answers[0]
    assert answer.mode == "llm"
    assert answer.answer == "Five days [1]."
    assert answer.cited == (answer.retrieved[0].section,)
    assert answer.generation_ms is not None
    assert quoted[0].mode == "extractive"
    assert len(quoted[0].cited) == 3
    assert quoted[0].generation_ms is None
    assert refused[0].mode == "refused"
    assert refused[0].cited == ()


# --- The three commands, end to end -------------------------------------------------


def test_base_config_records_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GIT_COMMIT", "abc1234")

    config = base_config(make_settings("postgresql+psycopg://u:p@h/db"))

    assert set(config) == set(BASE_CONFIG_FIELDS)
    assert config["Commit"] == "abc1234"
    assert config["Embedding model"] == "BAAI/bge-small-en-v1.5"
    assert config["Top k"] == "5"
    assert set(BASE_CONFIG_FIELDS) <= set(REQUIRED_CONFIG_FIELDS)


def test_calibrate_writes_the_report_and_the_thresholds(
    migrated_database_url: str, tmp_path: Path, base: dict[str, str]
) -> None:
    embedders = {"on": FakeEmbedder(), "off": FakeEmbedder()}

    thresholds = calibrate(
        migrated_database_url, embedders, QUESTIONS, top_k=5, base=base, results_dir=tmp_path
    )

    assert set(thresholds) == {"on", "off"}
    assert load_thresholds(tmp_path / "sample-calibration.json") == thresholds
    report = (tmp_path / "sample-calibration.md").read_text(encoding="utf-8")
    assert "Keep the query instruction on" in report  # the fake ignores the instruction: a tie


def test_evaluate_retrieval_compares_markdown_and_pdf_with_both_settings(
    migrated_database_url: str, tmp_path: Path, base: dict[str, str]
) -> None:
    embedders = {"on": FakeEmbedder(), "off": FakeEmbedder()}

    runs = evaluate_retrieval(
        migrated_database_url,
        embedders,
        QUESTIONS,
        top_k=5,
        thresholds={"on": 0.3, "off": 0.25},
        base=base,
        results_dir=tmp_path,
    )

    assert [run.label for run in runs] == [
        "Markdown, instruction on",
        "Markdown, instruction off",
        "PDF, instruction on",
        "PDF, instruction off",
    ]
    assert [run.threshold for run in runs] == [0.3, 0.25, 0.3, 0.25]
    report = (tmp_path / "sample-retrieval.md").read_text(encoding="utf-8")
    assert "| | Markdown, instruction on | Markdown, instruction off |" in report
    data = json.loads((tmp_path / "sample-retrieval.json").read_text(encoding="utf-8"))
    assert len(data["runs"]) == 4


def test_evaluate_end_to_end_warms_up_the_llm_and_writes_a_report(
    migrated_database_url: str, tmp_path: Path, base: dict[str, str]
) -> None:
    llm = FakeLLM("Five days [1].")

    run = evaluate_end_to_end(
        migrated_database_url,
        FakeEmbedder(),
        llm,
        QUESTIONS,
        instruction=True,
        top_k=5,
        threshold=0.1,
        base=base,
        results_dir=tmp_path,
    )

    assert run.warm_up_ms is not None
    assert len(llm.calls) == 1 + 2  # the warm-up, then each question
    report = (tmp_path / "sample-end-to-end-fake.md").read_text(encoding="utf-8")
    assert "| LLM | fake-model (fake) |" in report


def test_end_to_end_stops_when_the_llm_is_not_ready(
    migrated_database_url: str, tmp_path: Path, base: dict[str, str]
) -> None:
    with pytest.raises(RuntimeError, match="isn't ready"):
        evaluate_end_to_end(
            migrated_database_url,
            FakeEmbedder(),
            FakeLLM(status="unavailable"),
            QUESTIONS,
            instruction=True,
            top_k=5,
            threshold=0.1,
            base=base,
            results_dir=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_chunk_rows_keep_their_section_names(migrated_database_url: str) -> None:
    with loaded(migrated_database_url) as engine, engine.connect() as conn:
        sections = set(conn.execute(select(DocumentChunk.section)).scalars())

    assert CARRY.section in sections
