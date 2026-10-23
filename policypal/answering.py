"""Turn a question into a grounded answer: retrieve -> threshold -> generate -> check citations.

The rules, in order:
1. If no policy chunk is similar enough (best similarity < MIN_SIMILARITY), refuse.
   The LLM is not called.
2. Without an LLM (LLM_PROVIDER=extractive), quote the top passages.
3. Otherwise ask the LLM, giving it the chunks that passed the threshold as excerpts [1]..[n].
   - If the LLM fails (down, timeout, ...), quote the passages and say why.
   - If the reply contains the refusal sentence, it is a refusal, even if it also cites
     an excerpt: the model is saying the excerpts don't answer the question.
   - Citation markers that don't match an excerpt are removed.
   - An answer needs a valid marker and some words besides the markers.
   - Otherwise quote the passages and say why.
Every answer states its mode, so a fallback is never silent.
"""

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Engine

from policypal.embeddings import Embedder
from policypal.llm.base import REFUSAL_SENTENCE, LLMError, LLMProvider
from policypal.retrieval import RetrievedChunk, retrieve
from policypal.vocabulary import FallbackReason, Mode

logger = logging.getLogger("policypal.answering")

# Extractive answers quote at most this many passages, exactly as written.
EXTRACTIVE_HEADING = "No AI summary available — the most relevant policy passages are below."
MAX_PASSAGES = 3

# A citation marker: [1], or a list such as [1, 3]. The spaces before it are captured so
# a removed marker doesn't leave a gap before the full stop.
_MARKER = re.compile(r"(\s*)\[(\d+(?:\s*,\s*\d+)*)\]")
# The refusal sentence ("could not" also counts). Apostrophes are made straight first.
_REFUSAL = re.compile(r"could(?:n't| not) find this in the policies", re.IGNORECASE)


@dataclass(frozen=True)
class Citation:
    # The [n] marker in the answer text. It is also the chunk's search rank: the excerpts
    # are the top search results that passed the threshold, numbered from 1.
    number: int
    chunk: RetrievedChunk


@dataclass(frozen=True)
class Reply:
    """What the user is told."""

    text: str
    mode: Mode
    citations: tuple[Citation, ...] = ()
    model: str | None = None  # the LLM that wrote or refused the answer, if one did
    fallback_reason: FallbackReason | None = None
    generation_ms: int | None = None  # time spent waiting for the LLM; None if not called


@dataclass(frozen=True)
class Source:
    """One retrieved chunk, whether or not the answer cites it."""

    rank: int  # 1 = most similar
    chunk: RetrievedChunk
    cited: bool  # shown to the user as a citation


@dataclass(frozen=True)
class Answer:
    """A reply plus how it was produced: everything retrieved (best first) and timings."""

    reply: Reply
    sources: tuple[Source, ...]
    retrieval_ms: int
    total_ms: int

    @property
    def top_similarity(self) -> float | None:
        """The best match's similarity; None when nothing was retrieved."""
        return self.sources[0].chunk.similarity if self.sources else None


def answer_question(
    question: str,
    *,
    engine: Engine,
    embedder: Embedder,
    llm: LLMProvider | None,
    top_k: int,
    min_similarity: float,
) -> Answer:
    """Answer one question. `llm=None` means no LLM is configured (extractive mode)."""
    started = time.perf_counter()
    retrieved = retrieve(engine, embedder, question, top_k)
    retrieval_ms = _ms_since(started)
    reply = build_reply(question, retrieved, llm, min_similarity)
    cited = {citation.chunk.chunk_id for citation in reply.citations}
    return Answer(
        reply=reply,
        sources=tuple(
            Source(rank, chunk, chunk.chunk_id in cited)
            for rank, chunk in enumerate(retrieved, start=1)
        ),
        retrieval_ms=retrieval_ms,
        total_ms=_ms_since(started),
    )


def build_reply(
    question: str,
    retrieved: Sequence[RetrievedChunk],
    llm: LLMProvider | None,
    min_similarity: float,
) -> Reply:
    """Apply the answering rules to search results (best first)."""
    excerpts = [chunk for chunk in retrieved if chunk.similarity >= min_similarity]
    if not excerpts:
        return Reply(REFUSAL_SENTENCE, "refused")
    if llm is None:
        return _extractive(excerpts)

    started = time.perf_counter()
    try:
        text = llm.generate(question, excerpts)
    except LLMError as error:
        # The question is never logged: users may type personal details into it.
        logger.warning("llm.fallback", extra={"reason": error.reason, "error": str(error)})
        return _extractive(excerpts, error.reason, _ms_since(started))
    generation_ms = _ms_since(started)

    if _REFUSAL.search(text.replace("’", "'")):
        return Reply(REFUSAL_SENTENCE, "refused", model=llm.model, generation_ms=generation_ms)
    text = _remove_invalid_markers(text, len(excerpts)).strip()
    numbers = _cited_numbers(text)
    has_words = re.search(r"[A-Za-z]", _MARKER.sub("", text)) is not None
    if numbers and has_words:
        citations = tuple(Citation(n, excerpts[n - 1]) for n in numbers)
        return Reply(text, "llm", citations, llm.model, generation_ms=generation_ms)
    reason: FallbackReason = "llm_empty_answer" if numbers else "llm_no_valid_citation"
    logger.warning("llm.fallback", extra={"reason": reason})
    return _extractive(excerpts, reason, generation_ms)


def _extractive(
    excerpts: Sequence[RetrievedChunk],
    fallback_reason: FallbackReason | None = None,
    generation_ms: int | None = None,
) -> Reply:
    """The no-LLM answer: the top passages quoted as written. It never writes new text, so it
    can't state anything the policies don't say."""
    shown = excerpts[:MAX_PASSAGES]
    citations = tuple(Citation(n, chunk) for n, chunk in enumerate(shown, start=1))
    passages = [
        f"[{c.number}] {c.chunk.document_title} — {c.chunk.section}\n{_quote(c.chunk.text)}"
        for c in citations
    ]
    return Reply(
        "\n\n".join([EXTRACTIVE_HEADING, *passages]),
        "extractive",
        citations,
        fallback_reason=fallback_reason,
        generation_ms=generation_ms,
    )


def _quote(text: str) -> str:
    """Markdown block quote, line by line."""
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _remove_invalid_markers(text: str, excerpt_count: int) -> str:
    """Keep only the numbers 1..excerpt_count in each marker; drop markers left empty."""

    def keep_valid(match: re.Match[str]) -> str:
        valid = [n.strip() for n in match[2].split(",") if 1 <= int(n) <= excerpt_count]
        return f"{match[1]}[{', '.join(valid)}]" if valid else ""

    return _MARKER.sub(keep_valid, text)


def _cited_numbers(text: str) -> list[int]:
    """The excerpt numbers cited in the text, in ascending order, without repeats."""
    return sorted({int(n) for match in _MARKER.finditer(text) for n in match[2].split(",")})


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
