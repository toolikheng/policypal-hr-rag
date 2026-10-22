from policypal.llm.extractive import EXTRACTIVE_HEADING, MAX_PASSAGES, extractive_text
from tests.helpers import retrieved_chunk


def test_heading_says_no_ai_summary() -> None:
    assert EXTRACTIVE_HEADING == (
        "No AI summary available — the most relevant policy passages are below."
    )
    assert MAX_PASSAGES == 3


def test_passages_are_quoted_as_written_with_their_source() -> None:
    table = "| Years | Days |\n|---|---|\n| 0-2 | 14 |"
    excerpts = [
        retrieved_chunk(title="Leave Policy", section="4.1 Annual Leave Entitlement", text=table),
        retrieved_chunk(
            title="Overtime Policy", section="5. Overtime Rates", text="Two times.\n\nOK."
        ),
    ]

    text = extractive_text(excerpts)

    assert text == (
        f"{EXTRACTIVE_HEADING}\n\n"
        "[1] Leave Policy — 4.1 Annual Leave Entitlement\n"
        "> | Years | Days |\n> |---|---|\n> | 0-2 | 14 |\n\n"
        "[2] Overtime Policy — 5. Overtime Rates\n"
        "> Two times.\n>\n> OK."
    )
