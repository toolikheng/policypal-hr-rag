"""The no-LLM answer: the most relevant policy passages, quoted exactly as written.

Used when LLM_PROVIDER=extractive, and as the fallback whenever an LLM answer can't be
used. It never writes new text, so it can't state anything the policies don't say.
"""

from collections.abc import Sequence

from policypal.retrieval import RetrievedChunk

EXTRACTIVE_HEADING = "No AI summary available — the most relevant policy passages are below."
MAX_PASSAGES = 3


def extractive_text(excerpts: Sequence[RetrievedChunk]) -> str:
    """Quote the excerpts as Markdown block quotes, labelled [1], [2], ... with their source.

    The caller passes at most MAX_PASSAGES excerpts.
    """
    passages = [
        f"[{number}] {excerpt.document_title} — {excerpt.section}\n{_quote(excerpt.text)}"
        for number, excerpt in enumerate(excerpts, start=1)
    ]
    return "\n\n".join([EXTRACTIVE_HEADING, *passages])


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
