"""Checks on the fictional sample policies themselves (the data, not the code)."""

import re
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POLICY_DIR = DATA_DIR / "policies"
UPLOAD_DEMO_DIR = DATA_DIR / "upload-demo"

FICTIONAL_LABEL = "FICTIONAL SAMPLE DATA — NOT A REAL COMPANY POLICY"

CORE_POLICY_SLUGS = [
    "leave-policy",
    "medical-claims-policy",
    "overtime-policy",
    "expense-claims-policy",
    "travel-policy",
    "code-of-conduct",
    "probation-and-confirmation-policy",
    "work-from-home-policy",
]
UPLOAD_DEMO_SLUG = "training-and-development-policy"

CORE_POLICIES = [POLICY_DIR / f"{slug}.md" for slug in CORE_POLICY_SLUGS]
UPLOAD_DEMO_POLICY = UPLOAD_DEMO_DIR / f"{UPLOAD_DEMO_SLUG}.md"
ALL_POLICIES = [*CORE_POLICIES, UPLOAD_DEMO_POLICY]

# Topics that no policy covers, so questions about them must be refused later.
UNCOVERED_TOPICS = {
    "bonus": r"\bbonus",
    "salary increments or pay reviews": r"increment|salary review|pay review|pay rise",
    "company car or car allowance": r"company car|car allowance|pool car",
    "gym or fitness membership": r"\bgym\b|fitness",
    "share or stock options": r"share option|stock option|share scheme|\bESOS\b",
    "childcare support": r"child ?care|nursery|creche",
    "long-service awards": r"long[- ]service",
    "relocation allowance": r"relocat",
    "sabbatical leave": r"sabbatical",
    "retirement": r"retire",
}

# The upload-demo policy's subject. The core set must not cover it, so the held-out
# document adds genuinely new information when it is uploaded.
HELD_OUT_TOPIC = r"\btraining\b|\bcourses?\b|training bond"

NUMBERED_HEADING = re.compile(r"^#{2,3} \d+(\.\d+)*\.? \S")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("##")]


def test_core_folder_holds_exactly_the_eight_planned_policies() -> None:
    assert sorted(p.stem for p in POLICY_DIR.glob("*.md")) == sorted(CORE_POLICY_SLUGS)


def test_upload_demo_policy_is_kept_out_of_the_auto_ingested_folder() -> None:
    assert [p.name for p in UPLOAD_DEMO_DIR.glob("*.md")] == [UPLOAD_DEMO_POLICY.name]
    assert not (POLICY_DIR / UPLOAD_DEMO_POLICY.name).exists()


@pytest.mark.parametrize("path", ALL_POLICIES, ids=lambda p: p.stem)
def test_policy_is_labelled_fictional_at_the_top(path: Path) -> None:
    first_lines = read(path).splitlines()[:5]

    assert any(FICTIONAL_LABEL in line for line in first_lines)


@pytest.mark.parametrize("path", ALL_POLICIES, ids=lambda p: p.stem)
def test_policy_states_reference_version_and_effective_date(path: Path) -> None:
    header = "\n".join(read(path).splitlines()[:15])

    for field in ("Document reference", "Version", "Effective date"):
        assert f"| {field} |" in header, f"{path.name} is missing '{field}'"


@pytest.mark.parametrize("path", ALL_POLICIES, ids=lambda p: p.stem)
def test_policy_has_one_title_and_numbered_section_headings(path: Path) -> None:
    text = read(path)

    assert len([line for line in text.splitlines() if line.startswith("# ")]) == 1
    section_headings = headings(text)
    assert len(section_headings) >= 6
    for heading in section_headings:
        assert NUMBERED_HEADING.match(heading), f"{path.name}: unnumbered heading {heading!r}"


def test_policy_titles_are_unique() -> None:
    titles = [read(p).splitlines()[0] for p in ALL_POLICIES]

    assert len(set(titles)) == len(titles)


@pytest.mark.parametrize("topic", UNCOVERED_TOPICS, ids=str)
def test_uncovered_topic_is_not_mentioned_in_any_policy(topic: str) -> None:
    pattern = re.compile(UNCOVERED_TOPICS[topic], re.IGNORECASE)

    mentions = [p.name for p in ALL_POLICIES if pattern.search(read(p))]

    assert mentions == [], f"'{topic}' must stay uncovered but appears in {mentions}"


def test_core_policies_do_not_cover_the_held_out_documents_topic() -> None:
    pattern = re.compile(HELD_OUT_TOPIC, re.IGNORECASE)

    mentions = [p.name for p in CORE_POLICIES if pattern.search(read(p))]

    assert mentions == []
