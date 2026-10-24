"""The answer vocabulary is defined once, in policypal.vocabulary.

The UI talks to the API over HTTP only and never imports the backend, so it keeps its own
copies of some values and reply shapes. These tests keep those copies in step.
"""

from typing import Literal, get_args, get_origin, get_type_hints

import pytest
from pydantic import BaseModel

from policypal.api import schemas
from policypal.ingest.pipeline import IngestStatus
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


# Each UI reply type and the API model it copies. Health is a deliberate subset: the UI
# reads only the fields it shows.
UI_COPIES = [
    (api_client.Health, schemas.HealthResponse),
    (api_client.Citation, schemas.CitationResponse),
    (api_client.Answer, schemas.AskResponse),
    (api_client.Document, schemas.DocumentSummary),
    (api_client.ChunkText, schemas.ChunkText),
    (api_client.Section, schemas.SectionResponse),
    (api_client.DocumentDetail, schemas.DocumentDetail),
    (api_client.UploadResult, schemas.UploadResponse),
    (api_client.IngestResult, schemas.IngestResultResponse),
    (api_client.QuestionCount, schemas.QuestionCountResponse),
    (api_client.FallbackCount, schemas.FallbackCountResponse),
    (api_client.FeedbackStats, schemas.FeedbackStatsResponse),
    (api_client.LatencyStats, schemas.LatencyStatsResponse),
    (api_client.Analytics, schemas.AnalyticsResponse),
]
SUBSETS = {api_client.Health}


def response_fields(model: type[BaseModel]) -> dict[str, object]:
    """A response model's JSON fields, including computed ones (e.g. AskResponse.refused)."""
    fields = {name: field.annotation for name, field in model.model_fields.items()}
    computed = {name: field.return_type for name, field in model.model_computed_fields.items()}
    return fields | computed


@pytest.mark.parametrize(("ui_type", "model"), UI_COPIES, ids=lambda v: v.__name__)
def test_each_ui_reply_type_has_the_api_response_fields(
    ui_type: type, model: type[BaseModel]
) -> None:
    ui_fields = get_type_hints(ui_type)
    api_fields = response_fields(model)

    if ui_type in SUBSETS:
        assert set(ui_fields) <= set(api_fields)
    else:
        assert set(ui_fields) == set(api_fields)
    # Where the UI lists the allowed values, they must be the API's values.
    for name, annotation in ui_fields.items():
        if get_origin(annotation) is Literal:
            assert values(annotation) == values(api_fields[name]), name


# Fields the UI branches on (the answer badge, the re-ingest warning). The table above
# compares values only where the UI lists them, so these must also be Literals.
BRANCHED_ON = [
    (api_client.Answer, "mode", Mode),
    (api_client.IngestResult, "status", IngestStatus),
]


@pytest.mark.parametrize(
    ("ui_type", "field", "api_values"),
    BRANCHED_ON,
    ids=[f"{ui_type.__name__}.{field}" for ui_type, field, _ in BRANCHED_ON],
)
def test_the_ui_lists_every_value_of_the_fields_it_branches_on(
    ui_type: type, field: str, api_values: object
) -> None:
    annotation = get_type_hints(ui_type)[field]

    assert get_origin(annotation) is Literal, field
    assert values(annotation) == values(api_values), field
