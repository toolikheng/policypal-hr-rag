"""What every LLM provider has in common.

A provider turns a question plus numbered policy excerpts into an answer that cites
them as [1], [2], ... The answering code checks those citations, so a provider is
never trusted to cite correctly. Adding a hosted provider later means one new class
with the same two methods.
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from policypal.retrieval import RetrievedChunk

# The exact sentence used for every refusal, whether the app or the model refuses.
REFUSAL_SENTENCE = "I couldn't find this in the policies."

# Why an LLM answer couldn't be used. Shown to the user as `fallback_reason`.
LLMErrorReason = Literal[
    "llm_unavailable",  # the service couldn't be reached
    "llm_timeout",  # no answer within the configured timeout
    "llm_model_missing",  # the model hasn't been downloaded
    "llm_error",  # the service returned an error
    "llm_bad_response",  # the reply wasn't in the expected format
]

LLMStatus = Literal["ok", "unavailable", "model_missing"]


class LLMError(Exception):
    """The provider couldn't produce an answer. The app falls back to quoting the policies."""

    def __init__(self, reason: LLMErrorReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class LLMProvider(Protocol):
    name: str  # e.g. "ollama"
    model: str  # e.g. "llama3.2:3b"

    def generate(self, question: str, excerpts: Sequence[RetrievedChunk]) -> str:
        """Answer from the excerpts, citing excerpt n (excerpts[n - 1]) as [n].

        Raises LLMError if no answer could be produced.
        """
        ...

    def status(self) -> LLMStatus:
        """A quick check for /health: is the service up and the model available?"""
        ...
