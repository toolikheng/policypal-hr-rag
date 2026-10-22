from pathlib import Path

import pytest

from policypal.ingest.chunking import MAX_WORDS, Chunk, chunk_document, embedding_text
from policypal.ingest.parsing import ParsedDocument, Section, parse_markdown
from tests.unit.test_sample_policies import CORE_POLICIES


def paragraph(label: str, words: int) -> str:
    return " ".join([label] + [f"w{i}" for i in range(words - 1)])


def document(*sections: Section) -> ParsedDocument:
    return ParsedDocument(title="Example Policy", sections=sections)


def section(heading: str, *paragraphs: str, parent: str | None = None) -> Section:
    path = (parent, heading) if parent else (heading,)
    return Section(heading=heading, path=path, text="\n\n".join(paragraphs))


def word_count(text: str) -> int:
    return len(text.split())


def test_short_section_becomes_one_chunk_with_its_metadata() -> None:
    doc = document(section("4.3 Carry Forward", "Up to five days.", parent="4. Annual Leave"))

    assert chunk_document(doc) == [
        Chunk(
            index=0,
            section="4.3 Carry Forward",
            section_path="4. Annual Leave > 4.3 Carry Forward",
            content="Up to five days.",
        )
    ]


def test_chunks_never_cross_sections_and_are_numbered_in_order() -> None:
    doc = document(
        section("1. Purpose", paragraph("a", 40)), section("2. Scope", paragraph("b", 40))
    )

    chunks = chunk_document(doc)

    assert [(c.index, c.section) for c in chunks] == [(0, "1. Purpose"), (1, "2. Scope")]


def test_long_section_is_split_between_paragraphs_with_one_paragraph_overlap() -> None:
    paragraphs = [paragraph(f"p{n}", 60) for n in range(6)]  # 360 words in total
    doc = document(section("5.2 Anti-Harassment", *paragraphs))

    contents = [c.content for c in chunk_document(doc, max_words=150)]

    assert contents == [
        "\n\n".join(paragraphs[0:2]),
        "\n\n".join(paragraphs[1:3]),
        "\n\n".join(paragraphs[2:4]),
        "\n\n".join(paragraphs[3:5]),
        "\n\n".join(paragraphs[4:6]),
    ]
    assert all(word_count(text) <= 150 for text in contents)


def test_paragraph_longer_than_the_limit_is_kept_whole_in_its_own_chunk() -> None:
    small, huge, tail = paragraph("small", 20), paragraph("huge", 200), paragraph("tail", 20)
    doc = document(section("7. Exclusions", small, huge, tail))

    contents = [c.content for c in chunk_document(doc, max_words=100)]

    # The huge paragraph can't share a chunk, and is too big to repeat as overlap.
    assert contents == [small, huge, tail]


def test_markdown_table_is_never_split() -> None:
    table = "\n".join(
        ["| Grade | Limit |", "|---|---|"]
        + [f"| G{i} | RM{i}00 one two three |" for i in range(12)]
    )
    doc = document(section("3.2 Limits", paragraph("intro", 30), table, paragraph("after", 30)))

    contents = [c.content for c in chunk_document(doc, max_words=60)]

    assert any(table in text for text in contents)
    assert all(text.count("|---|") <= 1 for text in contents)


def test_embedding_text_starts_with_document_title_and_section_path() -> None:
    chunk = Chunk(
        index=0, section="4.3 Carry", section_path="4. Leave > 4.3 Carry", content="Text."
    )

    assert embedding_text("Leave Policy", chunk) == "Leave Policy — 4. Leave > 4.3 Carry\nText."


def test_word_count_counts_whitespace_separated_words() -> None:
    chunk = Chunk(index=0, section="s", section_path="s", content="one two\n\nthree | four |")

    assert chunk.word_count == 6


@pytest.mark.parametrize("path", CORE_POLICIES, ids=lambda p: p.stem)
def test_real_policies_produce_chunks_within_the_size_limit(path: Path) -> None:
    chunks = chunk_document(parse_markdown(path.read_text(encoding="utf-8")))

    assert chunks
    assert all(chunk.word_count <= MAX_WORDS for chunk in chunks)


def test_the_long_anti_harassment_section_is_split() -> None:
    [conduct] = [p for p in CORE_POLICIES if p.stem == "code-of-conduct"]
    chunks = chunk_document(parse_markdown(conduct.read_text(encoding="utf-8")))

    harassment = [c for c in chunks if c.section == "5.2 Anti-Harassment"]
    assert len(harassment) >= 2
