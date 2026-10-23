"""The values that describe a question and its answer, defined once.

This module imports nothing from the app, so every other module can use it (the database
models, answering, analytics and the API schemas) without import cycles.
"""

from typing import Literal

# How an answer was produced.
Mode = Literal["llm", "extractive", "refused"]

# Why an LLM answer couldn't be used (raised by an LLM provider).
LLMErrorReason = Literal[
    "llm_unavailable",  # the service couldn't be reached
    "llm_timeout",  # no answer within the configured timeout
    "llm_model_missing",  # the model hasn't been downloaded
    "llm_error",  # the service returned an error
    "llm_bad_response",  # the reply wasn't in the expected format
]

# Why an answer quotes the policies instead of using the LLM's text. Shown to the user as
# `fallback_reason`. Stored answers keep the reason they were given, so analytics must
# also accept reasons that have since been renamed or removed.
FallbackReason = LLMErrorReason | Literal["llm_no_valid_citation", "llm_empty_answer"]

# Which client asked the question.
Channel = Literal["ui", "widget", "api"]

# A vote on an answer.
Rating = Literal["up", "down"]
