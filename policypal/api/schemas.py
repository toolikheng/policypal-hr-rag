"""Request and response models. The examples appear in Swagger at /docs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
)

from policypal.answering import Answer
from policypal.db import DatabaseStatus
from policypal.ingest.parsing import FileType
from policypal.ingest.pipeline import IngestStatus
from policypal.llm.base import LLMStatus
from policypal.models import Origin
from policypal.vocabulary import Channel, FallbackReason, Mode, Rating


class LLMHealth(BaseModel):
    provider: str = Field(description="ollama, or extractive when no LLM is configured.")
    model: str | None
    status: LLMStatus

    model_config = ConfigDict(from_attributes=True)  # built from llm.LLMInfo


HEALTH_UNAVAILABLE_EXAMPLE = {
    "status": "unavailable",
    "database": "unreachable",
    "llm": {"provider": "ollama", "model": "llama3.2:3b", "status": "ok"},
    "documents": None,
    "chunks": None,
    "version": "0.1.0",
}


class HealthResponse(BaseModel):
    database: DatabaseStatus
    llm: LLMHealth
    documents: int | None  # null when the database can't be checked
    chunks: int | None
    version: str

    @computed_field
    @property
    def status(self) -> Literal["ok", "degraded", "unavailable"]:
        """Overall status, derived from the checks so it can never disagree with them.

        degraded: the LLM isn't ready, so answers quote the policy text instead.
        """
        if self.database != "ok":
            return "unavailable"
        return "ok" if self.llm.status == "ok" else "degraded"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "database": "ok",
                    "llm": {"provider": "ollama", "model": "llama3.2:3b", "status": "ok"},
                    "documents": 8,
                    "chunks": 119,
                    "version": "0.1.0",
                },
                {
                    "status": "degraded",
                    "database": "ok",
                    "llm": {"provider": "ollama", "model": "llama3.2:3b", "status": "unavailable"},
                    "documents": 8,
                    "chunks": 119,
                    "version": "0.1.0",
                },
            ]
        }
    )


# --- Text that is stored in PostgreSQL --------------------------------------------------


def _storable(text: str) -> str:
    """PostgreSQL text can't hold the NUL character, so it is rejected here (422) rather
    than failing later when the text is saved (500)."""
    if "\x00" in text:
        raise ValueError("must not contain the NUL character")
    return text


# --- POST /ask ------------------------------------------------------------------------

Question = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=1000),
    AfterValidator(_storable),
]


class AskRequest(BaseModel):
    question: Question
    conversation_id: UUID | None = Field(
        default=None,
        description="Groups the questions of one chat. Leave it null to start a new one; "
        "an ID the server doesn't know yet is accepted as a new conversation.",
    )
    channel: Channel = "api"

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


# --- POST /feedback -------------------------------------------------------------------

Comment = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_storable)
]


class FeedbackRequest(BaseModel):
    message_id: UUID = Field(description="The message_id returned by POST /ask.")
    rating: Rating
    comment: Comment | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a",
                    "rating": "down",
                    "comment": "Didn't mention site workers",
                }
            ]
        }
    )


class FeedbackResponse(BaseModel):
    status: Literal["recorded"]

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "recorded"}]})


# --- /documents -------------------------------------------------------------------------


DOCUMENT_SUMMARY_EXAMPLE = {
    "id": 3,
    "slug": "leave-policy",
    "title": "Leave Policy",
    "file_type": "md",
    "origin": "sample",
    "chunks": 18,
    "updated_at": "2026-10-22T09:30:00Z",
}


class DocumentSummary(BaseModel):
    id: int
    slug: str = Field(description="Taken from the file name; identifies the policy.")
    title: str
    file_type: FileType
    origin: Origin = Field(description="sample (built in) or upload.")
    chunks: int
    updated_at: datetime

    # from_attributes: built from the catalogue's dataclasses.
    model_config = ConfigDict(
        from_attributes=True, json_schema_extra={"examples": [DOCUMENT_SUMMARY_EXAMPLE]}
    )


class ChunkText(BaseModel):
    id: int
    text: str

    model_config = ConfigDict(from_attributes=True)


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    section: str
    section_path: str = Field(description='Headings above it, e.g. "4. Annual Leave > 4.1 ..."')
    chunks: list[ChunkText]


class DocumentDetail(DocumentSummary):
    sections: list[SectionResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    **DOCUMENT_SUMMARY_EXAMPLE,
                    "sections": [
                        {
                            "section": "4.1 Annual Leave Entitlement",
                            "section_path": "4. Annual Leave > 4.1 Annual Leave Entitlement",
                            "chunks": [
                                {
                                    "id": 41,
                                    "text": "Annual leave depends on job grade and on "
                                    "completed years of service ...",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )


# --- POST /documents and /documents/reingest ---------------------------------------------


class UploadResponse(BaseModel):
    status: Literal["created", "updated", "unchanged"]
    document: DocumentSummary

    model_config = ConfigDict(from_attributes=True)


UPLOAD_EXAMPLE = {
    "status": "created",
    "document": {
        **DOCUMENT_SUMMARY_EXAMPLE,
        "id": 9,
        "slug": "training-and-development-policy",
        "title": "Training and Development Policy",
        "origin": "upload",
        "chunks": 14,
    },
}


class IngestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # built from pipeline.IngestResult

    slug: str
    status: IngestStatus = Field(
        description="created, updated, unchanged, removed (file gone), or skipped "
        "(an uploaded file whose slug belongs to a sample policy)."
    )
    chunks: int


class ReingestResponse(BaseModel):
    results: list[IngestResultResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "results": [
                        {"slug": "leave-policy", "status": "unchanged", "chunks": 18},
                        {
                            "slug": "training-and-development-policy",
                            "status": "unchanged",
                            "chunks": 14,
                        },
                    ]
                }
            ]
        }
    )


# --- GET /analytics -------------------------------------------------------------------


class FeedbackStatsResponse(BaseModel):
    count: int = Field(description="Votes on messages in the period.")
    up: int
    down: int
    feedback_rate: float | None = Field(
        description="Messages with a vote / all messages; null when there are no messages."
    )
    helpful_rate: float | None = Field(description="Up votes / all votes; null with no votes.")


class LatencyStatsResponse(BaseModel):
    overall: int | None
    llm: int | None
    extractive: int | None


class QuestionCountResponse(BaseModel):
    question: str = Field(description="Lower-cased and trimmed, so repeats are grouped.")
    count: int
    last_asked: datetime


class FallbackCountResponse(BaseModel):
    # Plain text, not FallbackReason: a stored answer keeps its reason even after the code
    # renames or drops it, and old rows must never break analytics.
    reason: str = Field(description="e.g. llm_timeout, llm_unavailable (shown as stored).")
    count: int


class AnalyticsResponse(BaseModel):
    period_days: int
    total_questions: int
    answered: int = Field(description="Answered by the LLM or by quoting the policy.")
    refused: int
    refusal_rate: float | None = Field(description="Refused / all; null with no messages.")
    feedback: FeedbackStatsResponse
    avg_latency_ms: LatencyStatsResponse = Field(
        description="Average total time to answer, by mode; null when there are none."
    )
    top_questions: list[QuestionCountResponse]
    unanswered_questions: list[QuestionCountResponse] = Field(
        description="Questions the policies didn't cover (refused)."
    )
    fallbacks: list[FallbackCountResponse] = Field(
        description="Answers that fell back to quoting the policy, by reason. Extractive "
        "answers when no LLM is configured are not fallbacks."
    )

    model_config = ConfigDict(
        json_schema_extra={
            # Illustrative numbers, not measurements.
            "examples": [
                {
                    "period_days": 30,
                    "total_questions": 42,
                    "answered": 35,
                    "refused": 7,
                    "refusal_rate": 0.1667,
                    "feedback": {
                        "count": 12,
                        "up": 9,
                        "down": 3,
                        "feedback_rate": 0.2857,
                        "helpful_rate": 0.75,
                    },
                    "avg_latency_ms": {"overall": 18450, "llm": 24300, "extractive": 850},
                    "top_questions": [
                        {
                            "question": "how many days of annual leave do i get?",
                            "count": 5,
                            "last_asked": "2026-10-23T08:15:00Z",
                        }
                    ],
                    "unanswered_questions": [
                        {
                            "question": "is there a bonus this year?",
                            "count": 3,
                            "last_asked": "2026-10-22T16:40:00Z",
                        }
                    ],
                    "fallbacks": [{"reason": "llm_timeout", "count": 2}],
                }
            ]
        }
    )
