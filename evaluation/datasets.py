"""The evaluation question sets: YAML files of questions with their expected sources.

Each question has:
- `id` and `question`;
- `type`: the main thing that makes it hard (see metrics.ANSWERABLE_TYPES and
  metrics.UNANSWERABLE_TYPES);
- `expected`: the policy sections that answer it. For hit@k, any one of them counts as
  found; a "two-section" question needs both, which the reports count separately ("both
  sections in the top 5"). Unanswerable questions have none;
- `note`: why the question is there, written together with the question (before any run).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evaluation.metrics import ANSWERABLE_TYPES, UNANSWERABLE_TYPES, Section

EVALUATION_DIR = Path(__file__).resolve().parent
GOLDEN_SET = EVALUATION_DIR / "golden_set.yaml"
DEV_SET = EVALUATION_DIR / "dev_set.yaml"
# Questions about the held-out Training policy, written after the sets above and the
# threshold were frozen. Reported separately, as the "unseen document" test.
HELD_OUT_SET = EVALUATION_DIR / "held_out_set.yaml"


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    type: str
    expected: tuple[Section, ...]
    note: str

    @property
    def answerable(self) -> bool:
        return bool(self.expected)


@dataclass(frozen=True)
class QuestionSet:
    name: str
    questions: tuple[EvalQuestion, ...]


def load_question_set(path: Path) -> QuestionSet:
    """Read and check a question set. A mistake in the file stops the run with a clear
    message instead of producing misleading numbers."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = tuple(_question(item) for item in data["questions"])
    ids = [question.id for question in questions]
    duplicates = sorted({qid for qid in ids if ids.count(qid) > 1})
    if duplicates:
        raise ValueError(f"{path.name}: duplicate id '{duplicates[0]}'")
    return QuestionSet(name=data["name"], questions=questions)


def _question(item: dict[str, Any]) -> EvalQuestion:
    for key in ("id", "question", "type", "note"):
        if not item.get(key):
            raise ValueError(f"question {item.get('id', '?')}: missing '{key}'")
    qid, kind = item["id"], item["type"]
    expected = tuple(Section(s["document"], s["section"]) for s in item.get("expected") or [])
    if kind in UNANSWERABLE_TYPES:
        if expected:
            raise ValueError(
                f"question {qid}: an unanswerable question must have no expected sections"
            )
    elif kind not in ANSWERABLE_TYPES:
        raise ValueError(f"question {qid}: unknown type '{kind}'")
    elif kind == "two-section" and len(expected) != 2:
        raise ValueError(
            f"question {qid}: a two-section question needs exactly two expected sections"
        )
    elif not expected:
        raise ValueError(
            f"question {qid}: an answerable question needs at least one expected section"
        )
    return EvalQuestion(qid, item["question"], kind, expected, item["note"])
