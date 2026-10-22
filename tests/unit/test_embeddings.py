"""SentenceTransformerEmbedder, tested with a stand-in for the sentence_transformers library
so no model is downloaded or loaded."""

import sys
import types
from typing import Any

import numpy as np
import pytest

from policypal.embeddings import SentenceTransformerEmbedder

BGE_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class StubSentenceTransformer:
    """Records every encode call instead of running a model."""

    instances: list["StubSentenceTransformer"] = []

    def __init__(self, model_name: str, device: str) -> None:
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []
        StubSentenceTransformer.instances.append(self)

    def get_embedding_dimension(self) -> int:
        return 3

    def encode_query(self, sentences: Any, **kwargs: Any) -> np.ndarray:
        self.calls.append(("query", sentences, kwargs))
        return np.array([0.6, 0.8, 0.0])

    def encode_document(self, sentences: Any, **kwargs: Any) -> np.ndarray:
        self.calls.append(("document", sentences, kwargs))
        return np.array([[1.0, 0.0, 0.0] for _ in sentences])


@pytest.fixture
def stub_model(monkeypatch: pytest.MonkeyPatch) -> type[StubSentenceTransformer]:
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = StubSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    StubSentenceTransformer.instances.clear()
    return StubSentenceTransformer


def test_question_is_embedded_with_the_query_instruction(
    stub_model: type[StubSentenceTransformer],
) -> None:
    embedder = SentenceTransformerEmbedder("some/model", query_instruction=BGE_INSTRUCTION)

    vector = embedder.embed_query("How many days of annual leave do I get?")

    [model] = stub_model.instances
    [(kind, sentence, options)] = model.calls
    assert kind == "query"
    assert sentence == "How many days of annual leave do I get?"
    assert options["prompt"] == BGE_INSTRUCTION
    assert options["normalize_embeddings"] is True
    assert vector == [0.6, 0.8, 0.0]


@pytest.mark.parametrize("kind", ["query", "document"])
def test_no_progress_bar_is_drawn(stub_model: type[StubSentenceTransformer], kind: str) -> None:
    # The library draws one when logging is at INFO, which breaks the JSON-only logs.
    embedder = SentenceTransformerEmbedder("some/model", query_instruction=BGE_INSTRUCTION)

    if kind == "query":
        embedder.embed_query("Q?")
    else:
        embedder.embed_documents(["Text."])

    [(_, _, options)] = stub_model.instances[0].calls
    assert options["show_progress_bar"] is False


def test_empty_instruction_embeds_the_question_as_written(
    stub_model: type[StubSentenceTransformer],
) -> None:
    # An explicit empty prompt also stops the library adding a model-defined default.
    embedder = SentenceTransformerEmbedder("some/model", query_instruction="")

    embedder.embed_query("Can I work from home?")

    [(_, _, options)] = stub_model.instances[0].calls
    assert options["prompt"] == ""


def test_policy_passages_never_get_the_query_instruction(
    stub_model: type[StubSentenceTransformer],
) -> None:
    embedder = SentenceTransformerEmbedder("some/model", query_instruction=BGE_INSTRUCTION)

    vectors = embedder.embed_documents(["Leave Policy — 4. Annual Leave\nSixteen days."])

    [(kind, sentences, options)] = stub_model.instances[0].calls
    assert kind == "document"
    assert sentences == ["Leave Policy — 4. Annual Leave\nSixteen days."]
    assert BGE_INSTRUCTION not in str(options)
    assert vectors == [[1.0, 0.0, 0.0]]
