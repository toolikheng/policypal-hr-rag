"""Split sections into chunks small enough to embed well.

Rules:
1. A chunk never crosses a section boundary, so every chunk has exactly one citation.
2. A section of up to MAX_WORDS words stays whole.
3. A longer section is split between paragraphs. The last paragraph of one chunk is
   repeated at the start of the next (overlap), so context isn't lost at the cut.
4. Paragraphs are never split. A Markdown table has no blank lines inside it, so it
   counts as one paragraph and is never split either.
"""

from dataclasses import dataclass

from policypal.ingest.parsing import ParsedDocument

# About 250 words is ~330 tokens: comfortably inside the embedding model's 512-token limit.
MAX_WORDS = 250
# Bump this whenever the rules above change, so ingestion re-chunks every document.
CHUNKER_VERSION = 1


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str
    section_path: str
    content: str

    @property
    def word_count(self) -> int:
        return len(self.content.split())


def chunk_document(document: ParsedDocument, max_words: int = MAX_WORDS) -> list[Chunk]:
    pieces = [
        (section, text)
        for section in document.sections
        for text in split_into_chunks(section.text, max_words)
    ]
    return [
        Chunk(index, section.heading, " > ".join(section.path), text)
        for index, (section, text) in enumerate(pieces)
    ]


def split_into_chunks(text: str, max_words: int) -> list[str]:
    """Pack whole paragraphs into chunks of at most max_words, with one-paragraph overlap.

    A single paragraph longer than max_words becomes a chunk on its own.
    """
    chunks: list[list[str]] = [[]]
    for paragraph in text.split("\n\n"):
        current = chunks[-1]
        if current and _words(*current, paragraph) > max_words:
            previous = current[-1]
            overlap = [previous] if _words(previous, paragraph) <= max_words else []
            chunks.append([*overlap, paragraph])
        else:
            current.append(paragraph)
    return ["\n\n".join(paragraphs) for paragraphs in chunks]


def embedding_text(document_title: str, chunk: Chunk) -> str:
    """The text that gets embedded: a header naming the document and section, then the chunk.

    Without the header, similar sections in different policies (for example two
    "Eligibility" sections) would get almost the same vector.
    """
    return f"{document_title} — {chunk.section_path}\n{chunk.content}"


def _words(*paragraphs: str) -> int:
    return sum(len(paragraph.split()) for paragraph in paragraphs)
