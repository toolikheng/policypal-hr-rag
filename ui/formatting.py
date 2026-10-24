"""Small pure helpers that turn API replies into text for the pages (tested without Streamlit)."""

from datetime import UTC, datetime
from typing import Any, Literal

# Why the API quoted the policies instead of giving an AI answer, in plain words.
_FALLBACK_REASONS = {
    "llm_unavailable": "the AI model couldn't be reached",
    "llm_timeout": "the AI model took too long",
    "llm_model_missing": "the AI model isn't downloaded yet",
    "llm_error": "the AI model returned an error",
    "llm_bad_response": "the AI model returned an error",
    "llm_no_valid_citation": "the AI answer didn't cite the policies",
    "llm_empty_answer": "the AI answer was empty",
}


def safe_markdown(text: str) -> str:
    """Text from the API (policies, LLM answers), made safe to show with st.markdown.

    A browser loads a Markdown image (`![alt](url)` or `![alt][ref]`) by itself, so a
    policy or an answer could make every viewer call any server. Escaping the "!" turns
    it into an ordinary link, which needs a click. (Streamlit already escapes HTML.)
    """
    return text.replace("![", "\\![")


def badge(answer: dict[str, Any]) -> str:
    """One line saying how the answer was produced (the API's `mode`)."""
    if answer["mode"] == "llm":
        return f"🤖 AI answer from the policies ({answer['model']})"
    if answer["mode"] == "refused":
        return "🚫 Not covered by the policies"
    reason = answer["fallback_reason"]
    if reason is None:
        return "📄 Policy text (AI answers are switched off)"
    return f"📄 Policy text (no AI answer: {_FALLBACK_REASONS.get(reason, reason)})"


def source_label(citation: dict[str, Any]) -> str:
    """'[1] Leave Policy — 4.1 Annual Leave Entitlement · 0.77' (similarity, not a probability)."""
    return (
        f"[{citation['number']}] {citation['document_title']} — {citation['section']}"
        f" · {citation['similarity']:.2f}"
    )


def section_text(document: dict[str, Any], section: str) -> str:
    """The whole section, from its chunks in order.

    A long section's chunks repeat one paragraph where they join, so repeats are dropped.
    """
    paragraphs: list[str] = []
    for item in document["sections"]:
        if item["section"] != section:
            continue
        for chunk in item["chunks"]:
            for paragraph in chunk["text"].split("\n\n"):
                if paragraph not in paragraphs:
                    paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def upload_summary(result: dict[str, Any]) -> str:
    """'Training Policy: created (11 chunks).'"""
    document = result["document"]
    return f"{document['title']}: {result['status']} ({document['chunks']} chunks)."


# How a page shows the result of an action: st.success, st.warning or st.error.
NoticeLevel = Literal["success", "warning", "error"]

# Re-ingest statuses for a file whose current content isn't searchable afterwards.
_NOT_LOADED = ("failed", "skipped")


def reingest_notice(results: list[dict[str, Any]]) -> tuple[NoticeLevel, str]:
    """The level and message for a re-ingest, decided from the per-file statuses.

    'Re-ingested 9 policies: 8 unchanged, 1 removed.' (statuses in order of first
    appearance) is a success. If any file failed or was skipped, it is a warning that
    names them: '... Not loaded: broken-policy (failed).'
    """
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    noun = "policy" if len(results) == 1 else "policies"
    parts = ", ".join(f"{count} {status}" for status, count in counts.items())
    message = f"Re-ingested {len(results)} {noun}: {parts}."
    not_loaded = [r for r in results if r["status"] in _NOT_LOADED]
    if not not_loaded:
        return "success", message
    names = ", ".join(f"{r['slug']} ({r['status']})" for r in not_loaded)
    return "warning", f"{message} Not loaded: {names}."


def fallback_label(reason: str) -> str:
    """'the AI model took too long (llm_timeout)'; an unknown reason is shown as it is."""
    words = _FALLBACK_REASONS.get(reason)
    return f"{words} ({reason})" if words else reason


def percent(rate: float | None) -> str:
    """'75%', '33.3%', or '—' when there is no rate (nothing to divide by)."""
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}".removesuffix(".0") + "%"


def seconds(ms: int | None) -> str:
    """'18.5 s', or '—' when there is no average."""
    return "—" if ms is None else f"{ms / 1000:.1f} s"


def short_time(iso: str) -> str:
    """'2026-10-23T10:36:28.391104Z' -> '2026-10-23 10:36 UTC'."""
    return datetime.fromisoformat(iso).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
