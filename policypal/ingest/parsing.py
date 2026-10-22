"""Turn a policy file (Markdown or PDF) into a title and a list of sections.

A section is one heading, the text under it, and the path of headings above it, e.g.
path ("4. Annual Leave", "4.3 Carry Forward of Annual Leave"). Citations are built from
this, so every piece of text keeps track of where it came from.
"""

import io
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError

# Text before the first heading (fictional-data label, reference, version, dates).
DOCUMENT_INFO_HEADING = "Document information"


@dataclass(frozen=True)
class Section:
    heading: str
    path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    sections: tuple[Section, ...]


# One line of a document: a heading with its level (1 = top), or body text (level 0).
# An empty body line marks a paragraph break.
Line = tuple[int, str]


def assemble(title: str, lines: Iterable[Line]) -> ParsedDocument:
    """Group lines into sections. Headings with no text of their own only appear in paths."""
    sections: list[Section] = []
    path = [DOCUMENT_INFO_HEADING]
    body: list[str] = []

    def close_section() -> None:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
        if text:
            sections.append(Section(heading=path[-1], path=tuple(path), text=text))
        body.clear()

    for level, text in lines:
        if level == 0:
            body.append(text)
        else:
            close_section()
            # The document-information pseudo-section is never part of a real path.
            parents = [] if path == [DOCUMENT_INFO_HEADING] else path[: level - 1]
            path = [*parents, text]
    close_section()

    if not sections:
        raise ValueError("The document has no text.")
    return ParsedDocument(title=title, sections=tuple(sections))


# --- Markdown -----------------------------------------------------------------------

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_markdown(text: str) -> ParsedDocument:
    """`# Title` is the document title; `##` is a level-1 section, `###` level 2, and so on."""
    title: str | None = None
    lines: list[Line] = []
    for raw in text.splitlines():
        heading = _MARKDOWN_HEADING.match(raw)
        if heading and len(heading[1]) == 1 and title is None:
            title = heading[2]
        elif heading and len(heading[1]) > 1:
            lines.append((len(heading[1]) - 1, heading[2]))
        else:
            lines.append((0, raw.rstrip()))
    if title is None:
        raise ValueError("The Markdown file has no title line ('# Title').")
    return assemble(title, lines)


# --- PDF ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _PdfLine:
    page: int
    y: float
    size: float
    text: str


def parse_pdf(data: bytes) -> ParsedDocument:
    """Find headings by font size: lines printed bigger than the body text are headings.

    The biggest text on the first page is the title. Heading levels follow font size
    (biggest = level 1). Page headers and footers are removed, and a larger-than-normal
    vertical gap between lines starts a new paragraph.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        lines = [
            line for number, page in enumerate(reader.pages) for line in _read_page(number, page)
        ]
    except PyPdfError as exc:
        raise ValueError("The file is not a readable PDF.") from exc
    if not lines:
        raise ValueError(
            "The PDF has no text: no text could be extracted (scanned PDFs are not supported)."
        )
    lines = _remove_page_headers_and_footers(lines, page_count=len(reader.pages))

    chars_by_size: Counter[float] = Counter()
    for line in lines:
        chars_by_size[line.size] += len(line.text)
    body_size = chars_by_size.most_common(1)[0][0]

    title_size = max(line.size for line in lines if line.page == 0)
    title_lines = [line for line in lines if line.page == 0 and line.size == title_size]
    heading_sizes = sorted(
        {line.size for line in lines if body_size < line.size < title_size}, reverse=True
    )
    level_of = {size: rank + 1 for rank, size in enumerate(heading_sizes)}

    content = [line for line in lines if line not in title_lines]
    title = " ".join(line.text for line in title_lines)
    return assemble(title, _to_document_lines(content, level_of, body_size))


def _read_page(number: int, page: PageObject) -> list[_PdfLine]:
    """Collect text fragments with their position and size, merged into lines."""
    fragments: list[tuple[float, float, str]] = []

    def visit(text: str, cm: list[float], tm: list[float], font: object, size: float) -> None:
        text = text.replace("\n", "")
        if text.strip():
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            fragments.append((round(y, 1), round(size * (tm[3] or 1), 1), text))

    page.extract_text(visitor_text=visit)
    lines: list[_PdfLine] = []
    for y, size, text in fragments:
        if lines and abs(lines[-1].y - y) < 1:  # same baseline: same line
            last = lines.pop()
            lines.append(_PdfLine(number, last.y, max(last.size, size), last.text + text))
        else:
            lines.append(_PdfLine(number, y, size, text))
    return [_PdfLine(line.page, line.y, line.size, line.text.strip()) for line in lines]


def _remove_page_headers_and_footers(lines: list[_PdfLine], page_count: int) -> list[_PdfLine]:
    """Drop the same text, in the same place, on at least half of the pages.

    Digits are ignored so "Page 1 of 3" and "Page 2 of 3" count as the same line. The
    position matters: a table header repeated after a page break is content, not a footer.
    """
    if page_count < 2:
        return lines

    def key(line: _PdfLine) -> tuple[str, int]:
        return re.sub(r"\d+", "#", line.text), round(line.y)

    pages_with = Counter(k for k, _page in {(key(line), line.page) for line in lines})
    return [line for line in lines if pages_with[key(line)] < max(2, page_count / 2)]


def _to_document_lines(
    lines: list[_PdfLine], level_of: dict[float, int], body_size: float
) -> list[Line]:
    result: list[Line] = []
    for previous, line in zip([None, *lines[:-1]], lines, strict=True):
        level = level_of.get(line.size, 0)
        continues = (
            previous is not None
            and level_of.get(previous.size, 0) == level
            and _close_together(previous, line, body_size)
        )
        if level == 0:
            if not continues:
                result.append((0, ""))  # paragraph break (dropped if right after a heading)
            result.append((0, line.text))
        elif continues:
            result[-1] = (level, f"{result[-1][1]} {line.text}")  # heading wrapped onto 2 lines
        else:
            result.append((level, line.text))
    return result


def _close_together(previous: _PdfLine, line: _PdfLine, body_size: float) -> bool:
    """Consecutive lines of one paragraph are about one line-height apart."""
    if previous.page != line.page:
        return True
    return previous.y - line.y <= 1.5 * body_size
