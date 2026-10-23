"""The answering rules, tested without a database: given search results, what do we say?"""

import pytest

from policypal.answering import EXTRACTIVE_HEADING, build_reply
from policypal.llm.base import REFUSAL_SENTENCE, LLMError
from tests.fakes import FakeLLM
from tests.helpers import retrieved_chunk

THRESHOLD = 0.65

LEAVE = retrieved_chunk(
    chunk_id=11,
    document_id=1,
    title="Leave Policy",
    section="4.1 Annual Leave Entitlement",
    text="Employees with 2 to 5 years of service get 16 days.",
    similarity=0.81,
)
CARRY = retrieved_chunk(
    chunk_id=12,
    document_id=1,
    title="Leave Policy",
    section="4.3 Carry Forward of Annual Leave",
    text="Up to 5 unused days may be carried forward.",
    similarity=0.74,
)
OVERTIME = retrieved_chunk(
    chunk_id=31,
    document_id=3,
    title="Overtime Policy",
    section="5. Overtime Rates",
    text="Rest day work is paid at 2 times the hourly rate.",
    similarity=0.70,
)
WEAK = retrieved_chunk(
    chunk_id=99, title="Travel Policy", section="4. Accommodation", similarity=0.5
)


# --- Refusing before the LLM is called --------------------------------------------


def test_no_search_results_is_a_refusal() -> None:
    llm = FakeLLM()

    reply = build_reply("Is there a bonus?", [], llm, THRESHOLD)

    assert reply.mode == "refused"
    assert reply.text == REFUSAL_SENTENCE
    assert reply.citations == ()
    assert llm.calls == []


def test_best_match_below_the_threshold_is_refused_without_calling_the_llm() -> None:
    llm = FakeLLM()

    reply = build_reply("Can I bring my dog?", [WEAK], llm, THRESHOLD)

    assert reply.mode == "refused"
    assert reply.text == REFUSAL_SENTENCE
    assert reply.citations == ()
    assert reply.model is None
    assert reply.generation_ms is None
    assert llm.calls == []


def test_a_match_exactly_at_the_threshold_is_answered() -> None:
    at_threshold = retrieved_chunk(similarity=THRESHOLD)

    reply = build_reply("Annual leave?", [at_threshold], FakeLLM(), THRESHOLD)

    assert reply.mode == "llm"


def test_only_chunks_at_or_above_the_threshold_are_sent_to_the_llm() -> None:
    llm = FakeLLM()

    build_reply("Annual leave?", [LEAVE, CARRY, WEAK], llm, THRESHOLD)

    [(question, excerpts)] = llm.calls
    assert question == "Annual leave?"
    assert excerpts == [LEAVE, CARRY]


# --- Checking the LLM's citations ------------------------------------------------


def test_llm_answer_cites_the_document_and_section_it_used() -> None:
    llm = FakeLLM("You get 16 days [1].", model="llama3.2:3b")

    reply = build_reply("Annual leave?", [LEAVE, CARRY], llm, THRESHOLD)

    assert reply.mode == "llm"
    assert reply.text == "You get 16 days [1]."
    assert reply.model == "llama3.2:3b"
    assert reply.fallback_reason is None
    [citation] = reply.citations
    assert citation.number == 1
    assert citation.chunk.document_title == "Leave Policy"
    assert citation.chunk.section == "4.1 Annual Leave Entitlement"


def test_citations_are_only_the_excerpts_the_answer_cites() -> None:
    llm = FakeLLM("Rest days pay double [3]. You can carry 5 days [2][3].")

    reply = build_reply("Q?", [LEAVE, CARRY, OVERTIME], llm, THRESHOLD)

    assert [(c.number, c.chunk.chunk_id) for c in reply.citations] == [(2, 12), (3, 31)]


def test_out_of_range_markers_are_dropped_and_valid_ones_kept() -> None:
    llm = FakeLLM("You get 16 days [1]. Bonuses are 2 months [7]. Ask HR [0].")

    reply = build_reply("Q?", [LEAVE, CARRY], llm, THRESHOLD)

    assert reply.text == "You get 16 days [1]. Bonuses are 2 months. Ask HR."
    assert [c.number for c in reply.citations] == [1]


def test_invalid_numbers_are_removed_from_a_marker_list() -> None:
    llm = FakeLLM("You get 16 days [1, 4] and can carry 5 [2,1].")

    reply = build_reply("Q?", [LEAVE, CARRY], llm, THRESHOLD)

    assert reply.text == "You get 16 days [1] and can carry 5 [2, 1]."
    assert [c.number for c in reply.citations] == [1, 2]


def test_llm_answer_without_a_valid_citation_falls_back_to_policy_text() -> None:
    llm = FakeLLM("You get 16 days, see excerpt [9].")

    reply = build_reply("Q?", [LEAVE, CARRY], llm, THRESHOLD)

    assert reply.mode == "extractive"
    assert reply.fallback_reason == "llm_no_valid_citation"
    assert reply.text.startswith(EXTRACTIVE_HEADING)
    assert "excerpt [9]" not in reply.text
    assert [c.chunk for c in reply.citations] == [LEAVE, CARRY]
    assert reply.generation_ms is not None


@pytest.mark.parametrize(
    "llm_reply",
    [
        "I couldn't find this in the policies.",
        "  I couldn't find this in the policies  ",
        "I couldn’t find this in the policies.",  # curly apostrophe
        "Sorry, I could not find this in the policies.",
    ],
)
def test_llm_refusal_sentence_is_a_refusal(llm_reply: str) -> None:
    reply = build_reply("Q?", [LEAVE], FakeLLM(llm_reply, model="llama3.2:3b"), THRESHOLD)

    assert reply.mode == "refused"
    assert reply.text == REFUSAL_SENTENCE
    assert reply.citations == ()
    assert reply.model == "llama3.2:3b"
    assert reply.fallback_reason is None


# The first two are real llama3.2:3b replies from the Phase 5 evaluation (golden g01, g22):
# the model said the excerpt didn't answer the question but still cited it.
@pytest.mark.parametrize(
    "llm_reply",
    [
        "According to policy excerpt [1] 9.3, if a public holiday falls on a rest day, the next"
        " working day is a paid holiday. However, this does not directly answer the question."
        " I couldn't find this in the policies.",
        "According to policy excerpt [1] 5.1.3, where meals are provided free, the allowance is"
        " reduced by one third for each main meal provided. However, this excerpt does not"
        " directly address the lodging allowance. I couldn’t find this in the policies.",
        "You get 16 days [1]. I couldn't find this in the policies for interns.",
    ],
)
def test_a_reply_with_the_refusal_sentence_is_a_refusal_even_with_a_citation(
    llm_reply: str,
) -> None:
    reply = build_reply("Q?", [LEAVE], FakeLLM(llm_reply, model="llama3.2:3b"), THRESHOLD)

    assert reply.mode == "refused"
    assert reply.text == REFUSAL_SENTENCE
    assert reply.citations == ()
    assert reply.model == "llama3.2:3b"
    assert reply.fallback_reason is None


# Replies like these came from llama3.2:1b in the Phase 2 latency measurement.
@pytest.mark.parametrize(
    "llm_reply",
    [
        "[1] [2] [3]\n\nI couldn't find this in the policies.",
        "[1]. Sorry, I could not find this in the policies.",
    ],
)
def test_markers_with_only_the_refusal_sentence_are_a_refusal(llm_reply: str) -> None:
    reply = build_reply("Q?", [LEAVE, CARRY, OVERTIME], FakeLLM(llm_reply), THRESHOLD)

    assert reply.mode == "refused"
    assert reply.text == REFUSAL_SENTENCE
    assert reply.citations == ()


@pytest.mark.parametrize("llm_reply", ["[1] [3.1.1]", "[1][2]", " [1]. ", "[2] - [1]"])
def test_an_answer_of_only_markers_falls_back_to_policy_text(llm_reply: str) -> None:
    reply = build_reply("Q?", [LEAVE, CARRY], FakeLLM(llm_reply), THRESHOLD)

    assert reply.mode == "extractive"
    assert reply.fallback_reason == "llm_empty_answer"
    assert reply.text.startswith(EXTRACTIVE_HEADING)


def test_a_short_cited_answer_is_still_an_answer() -> None:
    reply = build_reply("Can I accept cash?", [LEAVE], FakeLLM("No [1]."), THRESHOLD)

    assert reply.mode == "llm"
    assert reply.text == "No [1]."


def test_a_refusal_with_advice_but_no_citation_is_still_a_refusal() -> None:
    llm = FakeLLM("I couldn't find this in the policies. Please contact HR.")

    reply = build_reply("Q?", [LEAVE], llm, THRESHOLD)

    assert reply.mode == "refused"


# --- Falling back when the LLM fails ----------------------------------------------


@pytest.mark.parametrize(
    "reason",
    ["llm_unavailable", "llm_timeout", "llm_model_missing", "llm_error", "llm_bad_response"],
)
def test_llm_failure_falls_back_to_policy_text_with_the_reason(reason: str) -> None:
    llm = FakeLLM(error=LLMError(reason, "something went wrong"))  # type: ignore[arg-type]

    reply = build_reply("Q?", [LEAVE, CARRY], llm, THRESHOLD)

    assert reply.mode == "extractive"
    assert reply.fallback_reason == reason
    assert reply.model is None
    assert [c.chunk for c in reply.citations] == [LEAVE, CARRY]


def test_llm_failure_is_logged_without_the_question(caplog: pytest.LogCaptureFixture) -> None:
    llm = FakeLLM(error=LLMError("llm_timeout", "Ollama did not answer within 60 s."))

    build_reply("My manager Aminah refused my leave", [LEAVE], llm, THRESHOLD)

    [record] = [r for r in caplog.records if r.getMessage() == "llm.fallback"]
    assert record.levelname == "WARNING"
    assert record.reason == "llm_timeout"
    assert "Aminah" not in caplog.text


# --- Extractive mode (no LLM configured) ------------------------------------------


def test_without_an_llm_the_answer_quotes_the_top_passages() -> None:
    reply = build_reply("Q?", [LEAVE, CARRY, OVERTIME], None, THRESHOLD)

    assert reply.mode == "extractive"
    assert reply.fallback_reason is None
    assert reply.model is None
    assert reply.generation_ms is None
    assert [(c.number, c.chunk) for c in reply.citations] == [(1, LEAVE), (2, CARRY), (3, OVERTIME)]
    for chunk in (LEAVE, CARRY, OVERTIME):
        assert chunk.text in reply.text


def test_extractive_answer_quotes_each_passage_as_written_under_its_source() -> None:
    table = retrieved_chunk(
        title="Leave Policy",
        section="4.1 Annual Leave Entitlement",
        text="| Years | Days |\n|---|---|\n| 0-2 | 14 |",
        similarity=0.9,
    )
    paragraphs = retrieved_chunk(
        title="Overtime Policy",
        section="5. Overtime Rates",
        text="Two times.\n\nOK.",
        similarity=0.8,
    )

    reply = build_reply("Q?", [table, paragraphs], None, THRESHOLD)

    assert reply.text == (
        "No AI summary available — the most relevant policy passages are below.\n\n"
        "[1] Leave Policy — 4.1 Annual Leave Entitlement\n"
        "> | Years | Days |\n> |---|---|\n> | 0-2 | 14 |\n\n"
        "[2] Overtime Policy — 5. Overtime Rates\n"
        "> Two times.\n>\n> OK."
    )


def test_extractive_answer_shows_at_most_three_passages() -> None:
    chunks = [retrieved_chunk(chunk_id=n, text=f"Passage {n}.", similarity=0.9) for n in range(5)]

    reply = build_reply("Q?", chunks, None, THRESHOLD)

    assert [c.chunk.chunk_id for c in reply.citations] == [0, 1, 2]
    assert "Passage 3." not in reply.text


def test_without_an_llm_a_weak_match_is_still_refused() -> None:
    assert build_reply("Q?", [WEAK], None, THRESHOLD).mode == "refused"
