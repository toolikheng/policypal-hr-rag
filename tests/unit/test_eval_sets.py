"""The evaluation question sets: the loader's checks, and the golden and dev sets themselves."""

import re
from collections import Counter
from pathlib import Path

import pytest

from evaluation.datasets import DEV_SET, GOLDEN_SET, HELD_OUT_SET, QuestionSet, load_question_set
from evaluation.metrics import ANSWERABLE_TYPES, Section
from policypal.ingest.chunking import chunk_document
from policypal.ingest.parsing import file_type_of, parse_document
from tests.sample_data import (
    CORE_POLICY_SLUGS,
    HELD_OUT_TOPIC,
    POLICY_DIR,
    UNCOVERED_TOPICS,
    UPLOAD_DEMO_DIR,
    UPLOAD_DEMO_SLUG,
)

# The 16 hand-picked questions that set the provisional threshold in Phase 2. The
# evaluation sets must not reuse them, or the calibration would be tested on its own data.
THRESHOLD_PROBE_QUESTIONS = [
    "How many days of annual leave do I get after working here for six years?",
    "Can I bring unused annual leave into next year?",
    "How much is the overtime rate on a public holiday?",
    "What is the mileage rate when I drive my own car for work?",
    "Does the company pay for my spectacles?",
    "How long is the probation period for new staff?",
    "Can I work from home if I am still on probation?",
    "Am I allowed to accept a gift from a supplier?",
    "Can I bring my dog to the office?",
    "How do I book a meeting room at headquarters?",
    "What time does the staff canteen open?",
    "Is there a cash reward for referring a friend who gets hired?",
    "Do employees get a discount on the company's housing projects?",
    "How do I change the bank account my salary is paid into?",
    "What is the weather forecast for Kuala Lumpur tomorrow?",
    "Who won the football match last night?",
]

VALID_ITEM = """\
  - id: q1
    question: How many days of paternity leave can a father take?
    type: amendment
    expected:
      - {document: leave-policy, section: "6.2 Paternity Leave"}
    note: Amended from 3 to 7 days.
"""


def write_set(tmp_path: Path, items: str, name: str = "sample") -> Path:
    path = tmp_path / "set.yaml"
    path.write_text(f"name: {name}\nquestions:\n{items}", encoding="utf-8")
    return path


def normalised(question: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())


def sections_in(paths: list[Path]) -> set[Section]:
    found = set()
    for path in paths:
        document = parse_document(path.read_bytes(), file_type_of(path.name))
        found |= {Section(path.stem, chunk.section) for chunk in chunk_document(document)}
    return found


@pytest.fixture(scope="module")
def golden() -> QuestionSet:
    return load_question_set(GOLDEN_SET)


@pytest.fixture(scope="module")
def dev() -> QuestionSet:
    return load_question_set(DEV_SET)


# --- The loader ---------------------------------------------------------------------


def test_load_question_set_reads_each_question(tmp_path: Path) -> None:
    question_set = load_question_set(write_set(tmp_path, VALID_ITEM))

    assert question_set.name == "sample"
    [item] = question_set.questions
    assert item.id == "q1"
    assert item.type == "amendment"
    assert item.expected == (Section("leave-policy", "6.2 Paternity Leave"),)
    assert item.answerable
    assert item.note == "Amended from 3 to 7 days."


def test_an_unanswerable_question_has_no_expected_sections(tmp_path: Path) -> None:
    item = (
        "  - {id: u1, question: 'Is there a bonus?', type: uncovered-topic, note: Not covered.}\n"
    )

    [question] = load_question_set(write_set(tmp_path, item)).questions

    assert question.expected == ()
    assert not question.answerable


@pytest.mark.parametrize(
    ("items", "message"),
    [
        (VALID_ITEM + VALID_ITEM, "duplicate id 'q1'"),
        (VALID_ITEM.replace("amendment", "tricky"), "unknown type 'tricky'"),
        (VALID_ITEM.replace("type: amendment", "type: uncovered-topic"), "must have no expected"),
        (
            "  - {id: q2, question: 'Bonus?', type: plain, note: n}\n",
            "needs at least one expected section",
        ),
        (VALID_ITEM.replace("amendment", "two-section"), "needs exactly two expected sections"),
        (VALID_ITEM.replace("    note: Amended from 3 to 7 days.\n", ""), "missing 'note'"),
    ],
)
def test_load_question_set_rejects_a_bad_item(tmp_path: Path, items: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_question_set(write_set(tmp_path, items))


# --- The golden and dev sets --------------------------------------------------------


def test_golden_set_has_40_answerable_and_12_unanswerable_questions(golden: QuestionSet) -> None:
    types = Counter(item.type for item in golden.questions)

    assert sum(types[name] for name in ANSWERABLE_TYPES) == 40
    assert all(types[name] >= 5 for name in ANSWERABLE_TYPES), types
    assert types["uncovered-topic"] == 10
    assert types["missing-detail"] == 2


def test_golden_set_asks_five_questions_about_each_policy(golden: QuestionSet) -> None:
    # The first expected section of each answerable question names its main policy.
    policies = Counter(item.expected[0].document for item in golden.questions if item.answerable)

    assert policies == Counter({slug: 5 for slug in CORE_POLICY_SLUGS})


def test_dev_set_has_12_answerable_and_8_unanswerable_questions(dev: QuestionSet) -> None:
    answerable = [item for item in dev.questions if item.answerable]

    assert len(answerable) == 12
    assert len(dev.questions) - len(answerable) == 8
    assert {item.type for item in answerable} == set(ANSWERABLE_TYPES)


@pytest.mark.parametrize("folder", [POLICY_DIR, POLICY_DIR / "pdf"], ids=["md", "pdf"])
def test_every_expected_section_exists_in_the_policies(
    golden: QuestionSet, dev: QuestionSet, folder: Path
) -> None:
    files = sorted(folder.glob("*.md")) + sorted(folder.glob("*.pdf"))
    assert sorted(path.stem for path in files) == sorted(CORE_POLICY_SLUGS)
    existing = sections_in(files)

    expected = {s for item in golden.questions + dev.questions for s in item.expected}
    assert expected - existing == set()


def test_no_question_appears_twice_within_or_across_the_sets(
    golden: QuestionSet, dev: QuestionSet
) -> None:
    questions = Counter(normalised(item.question) for item in golden.questions + dev.questions)

    assert [question for question, count in questions.items() if count > 1] == []
    assert len({item.id for item in golden.questions + dev.questions}) == 72


def test_no_threshold_probe_question_is_reused(golden: QuestionSet, dev: QuestionSet) -> None:
    probes = {normalised(question) for question in THRESHOLD_PROBE_QUESTIONS}

    reused = [
        item.id for item in golden.questions + dev.questions if normalised(item.question) in probes
    ]

    assert reused == []


def test_no_question_is_about_the_held_out_documents_topic(
    golden: QuestionSet, dev: QuestionSet
) -> None:
    pattern = re.compile(HELD_OUT_TOPIC, re.IGNORECASE)

    assert [i.id for i in golden.questions + dev.questions if pattern.search(i.question)] == []


@pytest.mark.parametrize("topic", UNCOVERED_TOPICS, ids=str)
def test_each_reserved_uncovered_topic_has_one_golden_refusal_question(
    golden: QuestionSet, dev: QuestionSet, topic: str
) -> None:
    pattern = re.compile(UNCOVERED_TOPICS[topic], re.IGNORECASE)

    golden_matches = [item for item in golden.questions if pattern.search(item.question)]
    assert [item.type for item in golden_matches] == ["uncovered-topic"]
    # The dev set uses different topics, so calibration never sees these.
    assert [item.id for item in dev.questions if pattern.search(item.question)] == []


# --- The held-out set (the unseen Training policy) ------------------------------------


@pytest.fixture(scope="module")
def held_out() -> QuestionSet:
    return load_question_set(HELD_OUT_SET)


def test_held_out_set_has_8_answerable_and_2_unanswerable_questions(held_out: QuestionSet) -> None:
    assert sum(item.answerable for item in held_out.questions) == 8
    assert [item.type for item in held_out.questions if not item.answerable] == [
        "missing-detail",
        "missing-detail",
    ]


@pytest.mark.parametrize("suffix", [".md", ".pdf"])
def test_held_out_questions_expect_sections_of_the_training_policy(
    held_out: QuestionSet, suffix: str
) -> None:
    existing = sections_in([(UPLOAD_DEMO_DIR / UPLOAD_DEMO_SLUG).with_suffix(suffix)])

    expected = {section for item in held_out.questions for section in item.expected}
    assert {section.document for section in expected} == {UPLOAD_DEMO_SLUG}
    assert expected - existing == set()


def test_held_out_questions_are_new(
    held_out: QuestionSet, golden: QuestionSet, dev: QuestionSet
) -> None:
    earlier = {normalised(item.question) for item in golden.questions + dev.questions}
    earlier |= {normalised(question) for question in THRESHOLD_PROBE_QUESTIONS}

    assert [item.id for item in held_out.questions if normalised(item.question) in earlier] == []
