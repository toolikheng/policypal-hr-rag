"""Request and response models. The examples appear in Swagger at /docs."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

from policypal.answering import Answer, FallbackReason, Mode
from policypal.db import DatabaseStatus


class HealthResponse(BaseModel):
    database: DatabaseStatus
    documents: int | None  # null when the database can't be checked
    chunks: int | None
    version: str

    @computed_field
    @property
    def status(self) -> Literal["ok", "unavailable"]:
        """Overall status, derived from the checks so it can never disagree with them."""
        return "ok" if self.database == "ok" else "unavailable"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "database": "ok",
                    "documents": 8,
                    "chunks": 119,
                    "version": "0.1.0",
                }
            ]
        }
    )


class ErrorResponse(BaseModel):
    """Every error has a plain message in `detail` (validation errors list each problem)."""

    detail: str


def error_example(description: str, detail: str) -> dict[str, Any]:
    """An entry for a route's `responses=`, so Swagger shows the error and its message."""
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}},
    }


VALIDATION_ERROR_EXAMPLE = {
    "description": "The request is invalid, e.g. the question is empty or too long.",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "type": "string_too_short",
                        "loc": ["body", "question"],
                        "msg": "String should have at least 3 characters",
                        "input": "hi",
                    }
                ]
            }
        }
    },
}

DATABASE_UNAVAILABLE = error_example("The database can't be reached.", "Database unavailable.")


# --- POST /ask ------------------------------------------------------------------------

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class AskRequest(BaseModel):
    question: Question
    # Groups questions from one chat for logging; a new one is made if not given.
    conversation_id: UUID | None = None
    channel: Literal["ui", "widget", "api"] = "api"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "question": "How many days of annual leave do I get after 3 years?",
                    "conversation_id": None,
                    "channel": "ui",
                }
            ]
        }
    )


class CitationResponse(BaseModel):
    number: int = Field(description="The [n] marker in the answer.")
    document_id: int
    document_title: str
    section: str
    text: str = Field(description="The policy text the answer is based on.")
    similarity: float = Field(description="Cosine similarity to the question (not a probability).")


class LatencyResponse(BaseModel):
    retrieval: int
    generation: int | None = Field(description="Time waiting for the LLM; null if not called.")
    total: int


class AskResponse(BaseModel):
    message_id: UUID
    conversation_id: UUID
    answer: str
    mode: Mode = Field(description="llm, extractive (quoted policy text) or refused.")
    citations: list[CitationResponse]
    model: str | None = Field(description="The LLM that wrote or refused the answer, if any.")
    fallback_reason: FallbackReason | None = Field(
        description="Why an LLM answer wasn't used, e.g. llm_unavailable or llm_timeout."
    )
    latency_ms: LatencyResponse

    @computed_field
    @property
    def refused(self) -> bool:
        return self.mode == "refused"

    @classmethod
    def from_answer(cls, answer: Answer, message_id: UUID, conversation_id: UUID) -> "AskResponse":
        reply = answer.reply
        return cls(
            message_id=message_id,
            conversation_id=conversation_id,
            answer=reply.text,
            mode=reply.mode,
            citations=[
                CitationResponse(
                    number=citation.number,
                    document_id=citation.chunk.document_id,
                    document_title=citation.chunk.document_title,
                    section=citation.chunk.section,
                    text=citation.chunk.text,
                    similarity=round(citation.chunk.similarity, 4),
                )
                for citation in reply.citations
            ],
            model=reply.model,
            fallback_reason=reply.fallback_reason,
            latency_ms=LatencyResponse(
                retrieval=answer.retrieval_ms, generation=reply.generation_ms, total=answer.total_ms
            ),
        )


_LEAVE_TABLE = (
    "| Completed years of service | NE grades | E grades | M and SM grades |\n"
    "|---|---|---|---|\n"
    "| 2 years to less than 5 years | 14 days | 16 days | 20 days |"
)
_LEAVE_CITATION = {
    "number": 1,
    "document_id": 3,
    "document_title": "Leave Policy",
    "section": "4.1 Annual Leave Entitlement",
    "text": _LEAVE_TABLE,
    "similarity": 0.7605,
}
_IDS = {
    "message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a",
    "conversation_id": "0b9e44d1-7c2a-4f6e-8d0b-5a7e3c9f1d24",
}
# Illustrative values (not measurements).
ASK_EXAMPLES = {
    "answered": {
        "summary": "Answered by the LLM, with a citation",
        "value": {
            **_IDS,
            "answer": "After 3 years you get 14, 16 or 20 days, depending on your grade [1].",
            "mode": "llm",
            "citations": [_LEAVE_CITATION],
            "model": "llama3.2:3b",
            "fallback_reason": None,
            "latency_ms": {"retrieval": 40, "generation": 9100, "total": 9150},
            "refused": False,
        },
    },
    "extractive": {
        "summary": "The LLM was unavailable, so the policy text is quoted",
        "value": {
            **_IDS,
            "answer": "No AI summary available — the most relevant policy passages are below.\n\n"
            "[1] Leave Policy — 4.1 Annual Leave Entitlement\n> ...",
            "mode": "extractive",
            "citations": [_LEAVE_CITATION],
            "model": None,
            "fallback_reason": "llm_unavailable",
            "latency_ms": {"retrieval": 40, "generation": 3, "total": 45},
            "refused": False,
        },
    },
    "refused": {
        "summary": "Not covered by the policies",
        "value": {
            **_IDS,
            "answer": "I couldn't find this in the policies.",
            "mode": "refused",
            "citations": [],
            "model": None,
            "fallback_reason": None,
            "latency_ms": {"retrieval": 38, "generation": None, "total": 39},
            "refused": True,
        },
    },
}
