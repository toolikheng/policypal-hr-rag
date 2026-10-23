"""The answer vocabulary is defined once, in policypal.vocabulary.

The UI talks to the API over HTTP only and never imports the backend, so it keeps its own
copies of some values. These tests keep those copies in step with the backend.
"""

from typing import get_args, get_type_hints

from policypal.vocabulary import FallbackReason, LLMErrorReason, Mode
from ui import api_client
from ui.formatting import _FALLBACK_REASONS


def values(literal: object) -> set[str]:
    """Every value of a Literal, including Literals joined with |."""
    found: set[str] = set()
    for arg in get_args(literal):
        found |= values(arg) if get_args(arg) else {arg}
    return found


def test_fallback_reasons_include_every_llm_error() -> None:
    assert values(LLMErrorReason) < values(FallbackReason)


def test_the_ui_has_plain_words_for_every_fallback_reason() -> None:
    assert set(_FALLBACK_REASONS) == values(FallbackReason)


def test_the_ui_client_knows_every_mode() -> None:
    assert values(get_type_hints(api_client.Answer)["mode"]) == values(Mode)
