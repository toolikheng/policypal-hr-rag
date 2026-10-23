"""Small pure helpers that turn API replies into text for the pages (tested without Streamlit)."""

from typing import Any

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


def reingest_summary(results: list[dict[str, Any]]) -> str:
    """'Re-ingested 9 policies: 8 unchanged, 1 removed.' (statuses in order of first appearance)"""
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    noun = "policy" if len(results) == 1 else "policies"
    parts = ", ".join(f"{count} {status}" for status, count in counts.items())
    return f"Re-ingested {len(results)} {noun}: {parts}."
