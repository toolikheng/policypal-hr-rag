"""Run the evaluation:  python -m evaluation.run_eval calibrate | retrieval | end-to-end

Every run rebuilds its own database, `policypal_eval`, on the same server as the app's
database: it is emptied and loaded with exactly the 8 sample policies (from Markdown or
from PDF). So the results never depend on what the app's database holds, and the app's
documents, question history and uploads are never touched.

Commands (the Makefile targets eval-calibrate, eval and eval-llm run them in Docker):
- calibrate   dev set, search only, query instruction on and off: choose a refusal
              threshold for each and say whether the dev set favours turning it off
- retrieval   golden set, search only: Markdown and PDF, instruction on and off
- end-to-end  golden set through the full pipeline (--provider ollama or extractive),
              with the app's query-instruction setting and its dev-set threshold
"""

import argparse
import json
import logging
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url

from evaluation.datasets import (
    DEV_SET,
    EVALUATION_DIR,
    GOLDEN_SET,
    HELD_OUT_SET,
    QuestionSet,
    load_question_set,
)
from evaluation.metrics import (
    AnswerOutcome,
    Match,
    RetrievalOutcome,
    Section,
    choose_threshold,
    count_refusals,
    hit_rate,
    instruction_verdict,
    refused_at,
    sweep,
)
from evaluation.report import (
    SOURCE_NAMES,
    AnswerRun,
    RetrievalRun,
    Source,
    calibration_report,
    end_to_end_report,
    environment,
    retrieval_report,
    write_report,
)
from policypal.answering import answer_question
from policypal.config import Settings
from policypal.db import make_engine
from policypal.embeddings import Embedder, build_embedder
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file, ingest_folder
from policypal.llm import build_llm, describe_llm
from policypal.llm.base import LLMError, LLMProvider
from policypal.logging_setup import configure_logging
from policypal.models import Document, DocumentChunk
from policypal.retrieval import RetrievedChunk, retrieve

logger = logging.getLogger("policypal.evaluation")

EVAL_DATABASE = "policypal_eval"
# Each version of the results has its own folder. Commands write to, and read the
# thresholds from, the current one. v1: the first official results (dev set of 20
# questions). v2: after seeing v1's errors, with 20 conversational dev questions added
# and the refusal-sentence rule fixed.
RESULTS_VERSION = "v2"
RESULTS_DIR = EVALUATION_DIR / "results" / RESULTS_VERSION
ALEMBIC_INI = EVALUATION_DIR.parent / "alembic.ini"
POLICY_FOLDERS: dict[Source, Path] = {"md": SAMPLE_POLICIES_DIR, "pdf": SAMPLE_POLICIES_DIR / "pdf"}
# The held-out "unseen document": added as an upload, in the same format as the run.
# Not in the Docker image; the Makefile mounts data/upload-demo for the held-out runs.
_HELD_OUT_POLICY = SAMPLE_POLICIES_DIR.parent / "upload-demo" / "training-and-development-policy"
HELD_OUT_POLICIES: dict[Source, Sequence[Path]] = {
    source: [_HELD_OUT_POLICY.with_suffix(f".{source}")] for source in ("md", "pdf")
}
# The model card's instruction: what "instruction on" means, whatever the app is set to.
QUERY_INSTRUCTION: str = Settings.model_fields["embedding_query_instruction"].default
# Asked once before an LLM run so loading the model isn't counted. It is in no question set.
WARM_UP_QUESTION = "What does the Leave Policy cover?"

# Settings every report records. Each command adds the question set, the policies, the
# query instruction, the threshold and the LLM.
BASE_CONFIG_FIELDS = (
    "Date (UTC)",
    "Commit",
    "Embedding model",
    "Top k",
    "CPU",
    "RAM",
    "Operating system",
    "Python",
    "Docker",
)


# --- The evaluation database ----------------------------------------------------------


def eval_database_url(app_database_url: str) -> str:
    """The evaluation database: same server and login as the app's, another name."""
    url = make_url(app_database_url).set(database=EVAL_DATABASE)
    return url.render_as_string(hide_password=False)


def create_database_if_missing(database_url: str) -> bool:
    """Create the database if it doesn't exist yet. Returns True if it was created."""
    url = make_url(database_url)
    # CREATE DATABASE can't run inside a transaction, so this connection autocommits.
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).first()
            if exists:
                return False
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
            return True
    finally:
        server.dispose()


def load_policies(
    database_url: str, embedder: Embedder, source: Source, extra_files: Sequence[Path] = ()
) -> Engine:
    """Rebuild the evaluation database: migrate it, empty it, then ingest exactly the 8
    sample policies from `source` (plus any `extra_files`, as uploads). The caller disposes
    the returned engine."""
    create_database_if_missing(database_url)
    alembic = Config(str(ALEMBIC_INI))
    alembic.attributes["database_url"] = database_url
    command.upgrade(alembic, "head")
    engine = make_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE documents, conversations RESTART IDENTITY CASCADE"))
    results = ingest_folder(engine, embedder, POLICY_FOLDERS[source], origin="sample")
    results += [ingest_file(engine, embedder, path, origin="upload") for path in extra_files]
    failed = [result.slug for result in results if result.status not in ("created", "updated")]
    if failed:
        engine.dispose()
        raise RuntimeError(f"These policies could not be loaded: {', '.join(failed)}")
    return engine


# --- Running the questions ------------------------------------------------------------


def run_retrieval(
    engine: Engine, embedder: Embedder, questions: QuestionSet, top_k: int
) -> tuple[RetrievalOutcome, ...]:
    """Search for each question, as the app does, and record what was found."""
    slugs = _slugs(engine)
    outcomes = []
    for question in questions.questions:
        started = time.perf_counter()
        chunks = retrieve(engine, embedder, question.question, top_k)
        outcomes.append(
            RetrievalOutcome(
                question_id=question.id,
                question_type=question.type,
                expected=question.expected,
                retrieved=tuple(Match(_section(c, slugs), c.similarity) for c in chunks),
                retrieval_ms=_ms_since(started),
            )
        )
    return tuple(outcomes)


def run_end_to_end(
    engine: Engine,
    embedder: Embedder,
    llm: LLMProvider | None,
    questions: QuestionSet,
    *,
    top_k: int,
    min_similarity: float,
) -> tuple[AnswerOutcome, ...]:
    """Answer each question with the app's own answering function (nothing is saved)."""
    slugs = _slugs(engine)
    outcomes = []
    for question in questions.questions:
        answer = answer_question(
            question.question,
            engine=engine,
            embedder=embedder,
            llm=llm,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        reply = answer.reply
        outcomes.append(
            AnswerOutcome(
                question_id=question.id,
                question_type=question.type,
                expected=question.expected,
                mode=reply.mode,
                answer=reply.text,
                cited=tuple(_section(citation.chunk, slugs) for citation in reply.citations),
                fallback_reason=reply.fallback_reason,
                retrieved=tuple(
                    Match(_section(s.chunk, slugs), s.chunk.similarity) for s in answer.sources
                ),
                retrieval_ms=answer.retrieval_ms,
                generation_ms=reply.generation_ms,
                total_ms=answer.total_ms,
            )
        )
        # Progress for long LLM runs; the question text itself is never logged.
        logger.info(
            "eval.answered",
            extra={"question_id": question.id, "mode": reply.mode, "total_ms": answer.total_ms},
        )
    return tuple(outcomes)


# --- The three commands -----------------------------------------------------------------


def base_config(settings: Settings) -> dict[str, str]:
    """The settings every report records (BASE_CONFIG_FIELDS). The commit and the Docker
    version are only known on the host, so the Makefile passes them in."""
    return {
        "Date (UTC)": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        "Commit": os.environ.get("EVAL_GIT_COMMIT") or "not recorded (EVAL_GIT_COMMIT)",
        "Embedding model": settings.embedding_model,
        "Top k": str(settings.retrieval_top_k),
        **environment(),
    }


def calibrate(
    database_url: str,
    embedders: Mapping[str, Embedder],
    questions: QuestionSet,
    *,
    top_k: int,
    base: Mapping[str, str],
    results_dir: Path,
) -> dict[str, float]:
    """Choose a refusal threshold for each query-instruction setting ("on" and "off") on
    the dev set, write `<set>-calibration.md/.json`, and return the thresholds."""
    # Passages are embedded without the instruction, so either embedder can load them.
    engine = load_policies(database_url, embedders["on"], "md")
    try:
        runs, sweeps = {}, {}
        for setting, embedder in embedders.items():
            outcomes = run_retrieval(engine, embedder, questions, top_k)
            sweeps[setting] = sweep(outcomes)
            threshold = choose_threshold(sweeps[setting])
            runs[setting] = RetrievalRun("md", setting == "on", threshold, outcomes)
        policies = _describe_policies(engine, "md")
    finally:
        engine.dispose()

    verdict = instruction_verdict(on=_dev_scores(runs["on"]), off=_dev_scores(runs["off"]))
    thresholds = {setting: run.threshold for setting, run in runs.items()}
    config = {
        **base,
        "Question set": _describe_set(questions),
        "Policies": policies,
        "Query instruction": "on and off (both measured)",
        "Threshold": "chosen here, one for each instruction setting",
        "LLM": "none (search only)",
    }
    data = {
        "config": config,
        "thresholds": thresholds,
        "verdict": verdict,
        "runs": {setting: _run_data(run) for setting, run in runs.items()},
        "sweeps": {setting: [asdict(row) for row in rows] for setting, rows in sweeps.items()},
    }
    markdown = calibration_report(config, runs, sweeps, verdict)
    _save(results_dir, f"{questions.name}-calibration", markdown, data)
    return thresholds


def evaluate_retrieval(
    database_url: str,
    embedders: Mapping[str, Embedder],
    questions: QuestionSet,
    *,
    top_k: int,
    thresholds: Mapping[str, float],
    base: Mapping[str, str],
    results_dir: Path,
    extra_files: Mapping[Source, Sequence[Path]] | None = None,
) -> list[RetrievalRun]:
    """Search for every question with the policies loaded from Markdown, then from PDF,
    each with the query instruction on and off. Writes `<set>-retrieval.md/.json`.
    `extra_files` adds uploads per format (the held-out policy)."""
    runs: list[RetrievalRun] = []
    policies = []
    for source in ("md", "pdf"):
        extra = (extra_files or {}).get(source, ())
        engine = load_policies(database_url, embedders["on"], source, extra)
        try:
            for setting in ("on", "off"):
                outcomes = run_retrieval(engine, embedders[setting], questions, top_k)
                runs.append(RetrievalRun(source, setting == "on", thresholds[setting], outcomes))
            policies.append(_describe_policies(engine, source))
        finally:
            engine.dispose()

    config = {
        **base,
        "Question set": _describe_set(questions),
        "Policies": "; ".join(policies),
        "Query instruction": "on and off (both reported)",
        "Threshold": (
            f"from the dev set: {thresholds['on']:g} with the instruction,"
            f" {thresholds['off']:g} without"
        ),
        "LLM": "none (search only)",
    }
    data = {"config": config, "runs": [_run_data(run) for run in runs]}
    markdown = retrieval_report(config, runs, questions)
    _save(results_dir, f"{questions.name}-retrieval", markdown, data)
    return runs


def evaluate_end_to_end(
    database_url: str,
    embedder: Embedder,
    llm: LLMProvider | None,
    questions: QuestionSet,
    *,
    instruction: bool,
    top_k: int,
    threshold: float,
    base: Mapping[str, str],
    results_dir: Path,
    extra_files: Sequence[Path] = (),
) -> AnswerRun:
    """Answer every question with the full pipeline (Markdown policies). Writes
    `<set>-end-to-end-<provider>.md/.json`. Stops first if the LLM isn't ready, because
    every answer would then silently fall back to quoting."""
    info = describe_llm(llm)
    if info.status != "ok":
        raise RuntimeError(
            f"The LLM ({info.model}) isn't ready (status: {info.status})."
            " Start Ollama and wait until it is healthy."
        )
    engine = load_policies(database_url, embedder, "md", extra_files)
    try:
        warm_up_ms = _warm_up(engine, embedder, llm) if llm else None
        outcomes = run_end_to_end(
            engine, embedder, llm, questions, top_k=top_k, min_similarity=threshold
        )
        policies = _describe_policies(engine, "md")
    finally:
        engine.dispose()

    run = AnswerRun(info.provider, info.model, threshold, outcomes, warm_up_ms)
    config = {
        **base,
        "Question set": _describe_set(questions),
        "Policies": policies,
        "Query instruction": "on" if instruction else "off",
        "Threshold": f"{threshold:g} (from the dev set)",
        "LLM": (
            f"{info.model} ({info.provider})"
            if info.model
            else "none: extractive mode quotes the policies"
        ),
    }
    data = {"config": config, "run": asdict(run)}
    markdown = end_to_end_report(config, run, questions)
    _save(results_dir, f"{questions.name}-end-to-end-{info.provider}", markdown, data)
    return run


def load_thresholds(path: Path) -> dict[str, float]:
    """The thresholds the calibration chose, by instruction setting ("on" and "off")."""
    if not path.exists():
        raise RuntimeError(
            f"{path.name} not found: run the calibration first (make eval-calibrate)"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return {setting: float(value) for setting, value in data["thresholds"].items()}


# --- Command line ---------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation.run_eval", description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("calibrate", help="choose the refusal threshold on the dev set")
    retrieval = commands.add_parser("retrieval", help="search quality (md/pdf, on/off)")
    end_to_end = commands.add_parser("end-to-end", help="full answers through the pipeline")
    end_to_end.add_argument("--provider", choices=("ollama", "extractive"), required=True)
    for command_parser in (retrieval, end_to_end):
        command_parser.add_argument(
            "--held-out",
            action="store_true",
            help="the unseen-document test: held-out questions, with the Training policy added",
        )
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level)
    database_url = eval_database_url(settings.database_url)
    base = base_config(settings)
    top_k = settings.retrieval_top_k
    calibration_file = args.results_dir / "dev-calibration.json"
    logger.info("eval.started", extra={"command": args.command})
    held_out = getattr(args, "held_out", False)
    questions = load_question_set(HELD_OUT_SET if held_out else GOLDEN_SET)
    extra_files = HELD_OUT_POLICIES if held_out else {}

    if args.command == "end-to-end":
        instruction = bool(settings.embedding_query_instruction)
        thresholds = load_thresholds(calibration_file)
        evaluate_end_to_end(
            database_url,
            build_embedder(settings),
            build_llm(settings.model_copy(update={"llm_provider": args.provider})),
            questions,
            instruction=instruction,
            top_k=top_k,
            threshold=thresholds["on" if instruction else "off"],
            base=base,
            results_dir=args.results_dir,
            extra_files=extra_files.get("md", ()),
        )
        return

    embedders = {
        setting: build_embedder(settings.model_copy(update={"embedding_query_instruction": text}))
        for setting, text in (("on", QUERY_INSTRUCTION), ("off", ""))
    }
    if args.command == "calibrate":
        thresholds = calibrate(
            database_url,
            embedders,
            load_question_set(DEV_SET),
            top_k=top_k,
            base=base,
            results_dir=args.results_dir,
        )
        logger.info("eval.thresholds", extra={"thresholds": thresholds})
    else:
        evaluate_retrieval(
            database_url,
            embedders,
            questions,
            top_k=top_k,
            thresholds=load_thresholds(calibration_file),
            base=base,
            results_dir=args.results_dir,
            extra_files=extra_files,
        )


# --- Helpers --------------------------------------------------------------------------


def _warm_up(engine: Engine, embedder: Embedder, llm: LLMProvider) -> int:
    """Ask one question that is in no set, so loading the model isn't counted in the
    measured answers. Returns how long it took."""
    excerpts = retrieve(engine, embedder, WARM_UP_QUESTION, 1)
    started = time.perf_counter()
    try:
        llm.generate(WARM_UP_QUESTION, excerpts)
    except LLMError as error:
        raise RuntimeError(f"The LLM failed on the warm-up question: {error}") from error
    return _ms_since(started)


def _slugs(engine: Engine) -> dict[int, str]:
    with engine.connect() as conn:
        return {row.id: row.slug for row in conn.execute(select(Document.id, Document.slug))}


def _section(chunk: RetrievedChunk, slugs: Mapping[int, str]) -> Section:
    return Section(slugs[chunk.document_id], chunk.section)


def _describe_policies(engine: Engine, source: Source) -> str:
    with engine.connect() as conn:
        samples = conn.execute(
            select(func.count()).select_from(Document).where(Document.origin == "sample")
        ).scalar_one()
        uploads = conn.execute(select(Document.slug).where(Document.origin == "upload")).scalars()
        chunks = conn.execute(select(func.count()).select_from(DocumentChunk)).scalar_one()
        extra = "".join(f" + upload {slug}" for slug in uploads)
    return f"{samples} sample policies from {SOURCE_NAMES[source]}{extra} ({chunks} chunks)"


def _describe_set(questions: QuestionSet) -> str:
    answerable = sum(question.answerable for question in questions.questions)
    total = len(questions.questions)
    return (
        f"{questions.name} ({total} questions: {answerable} answerable,"
        f" {total - answerable} should be refused)"
    )


def _dev_scores(run: RetrievalRun) -> tuple[float, float]:
    """(section hit@5, balanced accuracy at the chosen threshold) for the instruction rule."""
    counts = count_refusals(
        (o.answerable, refused_at(o.top_similarity, run.threshold)) for o in run.outcomes
    )
    return hit_rate(run.outcomes, 5).value or 0.0, counts.balanced_accuracy or 0.0


def _run_data(run: RetrievalRun) -> dict[str, object]:
    return {"label": run.label, **asdict(run)}


def _save(results_dir: Path, name: str, markdown: str, data: Mapping[str, object]) -> None:
    markdown_path, json_path = write_report(results_dir, name, markdown, data)
    logger.info(
        "eval.report_written", extra={"markdown": str(markdown_path), "json": str(json_path)}
    )


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


if __name__ == "__main__":
    main()
