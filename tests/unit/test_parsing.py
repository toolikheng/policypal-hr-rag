import re

import pytest
from fpdf import FPDF

from policypal.ingest.parsing import DOCUMENT_INFO_HEADING, parse_markdown, parse_pdf
from tests.unit.test_sample_policies import (
    CORE_POLICY_SLUGS,
    FICTIONAL_LABEL,
    POLICY_DIR,
    UPLOAD_DEMO_DIR,
    UPLOAD_DEMO_SLUG,
)

EXAMPLE = """# Example Policy

> **FICTIONAL SAMPLE DATA — NOT A REAL COMPANY POLICY.** Made up for tests.

| Field | Detail |
|---|---|
| Document reference | EX-001 |

## 1. Purpose

Why this policy exists.

## 2. Leave

### 2.1 Annual Leave

| Years of service | Days |
|---|---|
| Less than 2 | 10 |
| 2 and above | 12 |

A second paragraph about annual leave.

### 2.2 Sick Leave

Sick leave text.
"""


def section(doc, heading):
    [match] = [s for s in doc.sections if s.heading == heading]
    return match


def test_markdown_title_comes_from_the_first_level_one_heading() -> None:
    assert parse_markdown(EXAMPLE).title == "Example Policy"


def test_markdown_headings_become_sections_and_empty_parents_are_skipped() -> None:
    doc = parse_markdown(EXAMPLE)

    # "2. Leave" has no text of its own, so it only appears in its children's paths.
    assert [s.heading for s in doc.sections] == [
        DOCUMENT_INFO_HEADING,
        "1. Purpose",
        "2.1 Annual Leave",
        "2.2 Sick Leave",
    ]
    assert section(doc, "2.1 Annual Leave").path == ("2. Leave", "2.1 Annual Leave")
    assert section(doc, "1. Purpose").path == ("1. Purpose",)


def test_text_before_the_first_section_becomes_document_information() -> None:
    info = section(parse_markdown(EXAMPLE), DOCUMENT_INFO_HEADING)

    assert FICTIONAL_LABEL in info.text
    assert "| Document reference | EX-001 |" in info.text


def test_markdown_tables_and_paragraphs_stay_intact() -> None:
    text = section(parse_markdown(EXAMPLE), "2.1 Annual Leave").text

    table = "| Years of service | Days |\n|---|---|\n| Less than 2 | 10 |\n| 2 and above | 12 |"
    assert text == table + "\n\nA second paragraph about annual leave."


def test_markdown_without_a_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="title"):
        parse_markdown("## 1. Purpose\n\nNo title above me.\n")


def test_markdown_without_any_text_is_rejected() -> None:
    with pytest.raises(ValueError, match="no text"):
        parse_markdown("# Empty Policy\n")


def test_bytes_that_are_not_a_pdf_are_rejected() -> None:
    with pytest.raises(ValueError, match="not a readable PDF"):
        parse_pdf(b"%PDF-1.7 this is not really a pdf")


def test_pdf_without_extractable_text_is_rejected() -> None:
    blank = FPDF()
    blank.add_page()

    with pytest.raises(ValueError, match="no text could be extracted"):
        parse_pdf(bytes(blank.output()))


# --- The committed PDFs must say the same thing as their Markdown source. ---

CORE_PAIRS = [(POLICY_DIR / f"{s}.md", POLICY_DIR / "pdf" / f"{s}.pdf") for s in CORE_POLICY_SLUGS]
DEMO_STEM = UPLOAD_DEMO_DIR / UPLOAD_DEMO_SLUG
DEMO_PAIR = (DEMO_STEM.with_suffix(".md"), DEMO_STEM.with_suffix(".pdf"))
PDF_PAIRS = [*CORE_PAIRS, DEMO_PAIR]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", text.lower()))


@pytest.mark.parametrize(("md_path", "pdf_path"), PDF_PAIRS, ids=lambda p: p.name)
def test_pdf_has_the_same_title_and_sections_as_its_markdown(md_path, pdf_path) -> None:
    from_md = parse_markdown(md_path.read_text(encoding="utf-8"))
    from_pdf = parse_pdf(pdf_path.read_bytes())

    assert from_pdf.title == from_md.title
    assert [s.path for s in from_pdf.sections] == [s.path for s in from_md.sections]


@pytest.mark.parametrize(("md_path", "pdf_path"), PDF_PAIRS, ids=lambda p: p.name)
def test_pdf_sections_contain_the_markdown_text(md_path, pdf_path) -> None:
    from_md = parse_markdown(md_path.read_text(encoding="utf-8"))
    from_pdf = parse_pdf(pdf_path.read_bytes())

    for md_section, pdf_section in zip(from_md.sections, from_pdf.sections, strict=True):
        missing = words(md_section.text) - words(pdf_section.text)
        assert not missing, f"{pdf_path.name} {md_section.heading}: missing {sorted(missing)[:10]}"


@pytest.mark.parametrize(("md_path", "pdf_path"), PDF_PAIRS, ids=lambda p: p.name)
def test_pdf_page_footers_are_removed(md_path, pdf_path) -> None:
    from_pdf = parse_pdf(pdf_path.read_bytes())

    for pdf_section in from_pdf.sections:
        assert not re.search(r"Page \d+ of \d+", pdf_section.text), pdf_section.heading


def test_pdf_keeps_the_fictional_label_in_document_information() -> None:
    from_pdf = parse_pdf((POLICY_DIR / "pdf" / "leave-policy.pdf").read_bytes())

    assert FICTIONAL_LABEL in section(from_pdf, DOCUMENT_INFO_HEADING).text


def test_pdf_paragraphs_are_separated_by_blank_lines() -> None:
    from_pdf = parse_pdf((POLICY_DIR / "pdf" / "code-of-conduct.pdf").read_bytes())

    harassment = section(from_pdf, "5.2 Anti-Harassment").text
    assert len(harassment.split("\n\n")) == 6  # clauses 5.2.1 to 5.2.6
