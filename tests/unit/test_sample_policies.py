"""Checks on the fictional sample policies themselves (the data, not the code)."""

import re
from pathlib import Path

import pytest

from tests.sample_data import (
    ALL_POLICIES,
    CORE_POLICIES,
    CORE_POLICY_SLUGS,
    FICTIONAL_LABEL,
    HELD_OUT_TOPIC,
    POLICY_DIR,
    UNCOVERED_TOPICS,
    UPLOAD_DEMO_DIR,
    UPLOAD_DEMO_POLICY,
    UPLOAD_DEMO_SLUG,
)

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


def test_every_policy_has_a_rendered_pdf_and_no_stray_pdfs_exist() -> None:
    assert sorted(p.stem for p in (POLICY_DIR / "pdf").glob("*.pdf")) == sorted(CORE_POLICY_SLUGS)
    assert [p.stem for p in UPLOAD_DEMO_DIR.glob("*.pdf")] == [UPLOAD_DEMO_SLUG]
