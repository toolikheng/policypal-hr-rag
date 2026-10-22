"""Render the Markdown policies to PDF.

The Markdown files are the source of truth. This script writes:
  data/policies/*.md     -> data/policies/pdf/*.pdf
  data/upload-demo/*.md  -> data/upload-demo/*.pdf

Run with `make pdfs`. It needs the DejaVu Sans font, which supports characters such as
"—" and "×" (on Ubuntu: sudo apt install fonts-dejavu-core). The output is
deterministic, so re-running it without changing the Markdown changes nothing in git.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import markdown
from fpdf import FPDF

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
JOBS = [
    (DATA_DIR / "policies", DATA_DIR / "policies" / "pdf"),
    (DATA_DIR / "upload-demo", DATA_DIR / "upload-demo"),
]
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
# A fixed creation date keeps the PDF bytes identical between runs.
FIXED_CREATION_DATE = datetime(2025, 1, 1, tzinfo=UTC)


class PolicyPdf(FPDF):
    def __init__(self, footer_text: str) -> None:
        super().__init__(format="A4")
        self.footer_text = footer_text

    def footer(self) -> None:
        # Repeated on every page, like a real policy PDF; the parser removes it again.
        self.set_y(-12)
        self.set_font("DejaVu", size=8)
        self.cell(0, 8, f"{self.footer_text} | Page {self.page_no()} of {{nb}}", align="C")


def render(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    title = text.splitlines()[0].removeprefix("# ").strip()
    reference = re.search(r"\| Document reference \| (\S+) \|", text)
    if reference is None:
        raise ValueError(f"{md_path.name}: no 'Document reference' row found")

    pdf = PolicyPdf(footer_text=f"{reference[1]} | {title}")
    pdf.set_creation_date(FIXED_CREATION_DATE)
    pdf.set_title(title)
    pdf.set_author("Binaan Maju Sdn Bhd (fictional sample data)")
    pdf.add_font("DejaVu", "", FONT_DIR / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", FONT_DIR / "DejaVuSans-Bold.ttf")
    pdf.set_margins(18, 18, 18)
    pdf.set_font("DejaVu", size=10)
    pdf.add_page()
    pdf.write_html(markdown.markdown(text, extensions=["tables"]))
    pdf.output(str(pdf_path))


def main() -> None:
    if not (FONT_DIR / "DejaVuSans.ttf").exists():
        raise SystemExit(f"DejaVu Sans not found in {FONT_DIR}: sudo apt install fonts-dejavu-core")
    for source_dir, output_dir in JOBS:
        output_dir.mkdir(parents=True, exist_ok=True)
        for md_path in sorted(source_dir.glob("*.md")):
            pdf_path = output_dir / f"{md_path.stem}.pdf"
            render(md_path, pdf_path)
            print(f"wrote {pdf_path.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
