"""The answer vocabulary is defined once, in policypal.vocabulary.

The UI talks to the API over HTTP only and never imports the backend, so it keeps its own
copies of some values and reply shapes. These tests keep those copies in step.
"""

from typing import get_args, get_type_hints

from policypal.api.schemas import AnalyticsResponse
from policypal.vocabulary import FallbackReason, LLMErrorReason, Mode
from ui import api_client
from ui.formatting import fallback_label


def values(literal: object) -> set[str]:
    """Every value of a Literal, including Literals joined with |."""
    found: set[str] = set()
    for arg in get_args(literal):
        found |= values(arg) if get_args(arg) else {arg}
    return found


def test_fallback_reasons_include_every_llm_error() -> None:
    assert values(LLMErrorReason) < values(FallbackReason)


def test_the_ui_has_plain_words_for_every_fallback_reason() -> None:
    # An unknown reason is shown as its bare code, so plain words mean the UI knows it.
    for reason in values(FallbackReason):
        assert fallback_label(reason) != reason, reason


def test_the_ui_client_knows_every_mode() -> None:
    assert values(get_type_hints(api_client.Answer)["mode"]) == values(Mode)


def typed_dict_fields(typed_dict: type) -> dict[str, object]:
    return get_type_hints(typed_dict)


def test_the_ui_analytics_type_has_the_api_response_fields() -> None:
    """The UI declares its own types for API replies; nested ones must match too."""
    ui_fields = typed_dict_fields(api_client.Analytics)

    assert set(ui_fields) == set(AnalyticsResponse.model_fields)
    for name in ("feedback", "avg_latency_ms"):
        nested = AnalyticsResponse.model_fields[name].annotation
        assert set(typed_dict_fields(ui_fields[name])) == set(nested.model_fields), name
