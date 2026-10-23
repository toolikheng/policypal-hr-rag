"""Turn a policy file (Markdown or PDF) into a title and a list of sections.

A section is one heading, the text under it, and the path of headings above it, e.g.
path ("4. Annual Leave", "4.3 Carry Forward of Annual Leave"). Citations are built from
this, so every piece of text keeps track of where it came from.

Both formats are first turned into the same simple form, a list of lines that are either
a Heading or a line of text, and then `assemble()` groups those lines into sections.
"""

import io
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError

FileType = Literal["md", "pdf"]
SUPPORTED_SUFFIXES: dict[str, FileType] = {".md": "md", ".pdf": "pdf"}

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


@dataclass(frozen=True)
class Heading:
    level: int  # 1 = top-level section, 2 = sub-section, ...
    text: str


# A line of a document: a heading, or a line of text ("" is a blank line between paragraphs).
Line = Heading | str


def file_type_of(filename: str) -> FileType:
    file_type = SUPPORTED_SUFFIXES.get(PurePath(filename).suffix.lower())
    if file_type is None:
        raise ValueError(f"Unsupported file '{filename}': only .md and .pdf files are supported.")
    return file_type


def parse_document(data: bytes, file_type: FileType) -> ParsedDocument:
    if file_type == "pdf":
        parsed = parse_pdf(data)
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("The Markdown file is not valid UTF-8 text.") from exc
        parsed = parse_markdown(text)
    # PostgreSQL text can't hold the NUL character, so such a document could never be saved.
    stored = [parsed.title, *(part for s in parsed.sections for part in (*s.path, s.text))]
    if any("\x00" in part for part in stored):
        raise ValueError("The document contains a NUL character, which can't be stored.")
    return parsed


def assemble(title: str, lines: Iterable[Line]) -> ParsedDocument:
    """Group lines into sections. Headings with no text of their own only appear in paths."""
    sections: list[Section] = []
    path: list[str] = []  # headings above the current line; empty before the first heading
    body: list[str] = []

    def close_section() -> None:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
        if text:
            section_path = tuple(path) or (DOCUMENT_INFO_HEADING,)
            sections.append(Section(heading=section_path[-1], path=section_path, text=text))
        body.clear()

    for line in lines:
        if isinstance(line, Heading):
            close_section()
            path = [*path[: line.level - 1], line.text]
        else:
            body.append(line)
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
            lines.append(Heading(level=len(heading[1]) - 1, text=heading[2]))
        else:
            lines.append(raw.rstrip())
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
    """Find structure from font sizes: text printed bigger than the body text is a heading.

    - Page headers and footers (same text, same place, on most pages) are removed.
    - The title is the first run of the biggest lines on page 1, if they are bigger than
      the body text; otherwise it is simply the first line.
    - Bigger-than-body lines after the title are headings; bigger font = higher level.
    - A larger-than-normal vertical gap between lines starts a new paragraph.
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

    body_size = _most_common_size(lines)
    start, end = _title_span(lines, body_size)
    title = " ".join(line.text for line in lines[start:end])
    content = lines[:start] + lines[end:]

    heading_sizes = sorted({line.size for line in content if line.size > body_size}, reverse=True)
    level_of = {size: rank + 1 for rank, size in enumerate(heading_sizes)}
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


def _most_common_size(lines: list[_PdfLine]) -> float:
    """The body text size: the font size used for the most characters."""
    chars_by_size: Counter[float] = Counter()
    for line in lines:
        chars_by_size[line.size] += len(line.text)
    return chars_by_size.most_common(1)[0][0]


def _title_span(lines: list[_PdfLine], body_size: float) -> tuple[int, int]:
    """Start and end index of the title lines: the first run of the biggest lines on the
    first page, or just the first line if nothing there is bigger than the body text."""
    first_page = [line for line in lines if line.page == lines[0].page]
    biggest = max(line.size for line in first_page)
    if biggest <= body_size:
        return 0, 1
    start = next(i for i, line in enumerate(lines) if line.size == biggest)
    end = start + 1
    while end < len(lines) and lines[end].size == biggest:
        end += 1
    return start, end


def _to_document_lines(
    lines: list[_PdfLine], level_of: dict[float, int], body_size: float
) -> list[Line]:
    result: list[Line] = []
    previous: _PdfLine | None = None
    for line in lines:
        level = level_of.get(line.size, 0)
        continues = (
            previous is not None
            and level_of.get(previous.size, 0) == level
            and _close_together(previous, line, body_size)
        )
        if level == 0:
            if not continues:
                result.append("")  # paragraph break (dropped if right after a heading)
            result.append(line.text)
        elif continues and isinstance(result[-1], Heading):
            result[-1] = Heading(level, f"{result[-1].text} {line.text}")  # wrapped heading
        else:
            result.append(Heading(level, line.text))
        previous = line
    return result


def _close_together(previous: _PdfLine, line: _PdfLine, body_size: float) -> bool:
    """Consecutive lines of one paragraph are about one line-height apart."""
    if previous.page != line.page:
        return True
    return previous.y - line.y <= 1.5 * body_size
