import logging
import uuid

from fastapi import APIRouter

from policypal.answering import answer_question
from policypal.api.deps import EmbedderDep, EngineDep, LLMDep, SettingsDep
from policypal.api.schemas import (
    ASK_EXAMPLES,
    DATABASE_UNAVAILABLE,
    VALIDATION_ERROR_EXAMPLE,
    AskRequest,
    AskResponse,
)

logger = logging.getLogger("policypal.api")

router = APIRouter(tags=["ask"])


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Answer a question from the policies, with citations",
    description=(
        "Searches the policies, then answers with the local LLM, citing each source as [n]. "
        "If no policy text is similar enough, the answer is \"I couldn't find this in the "
        'policies." If the LLM is unavailable, the most relevant policy text is quoted instead '
        "(`mode` = extractive, with a `fallback_reason`)."
    ),
    responses={
        200: {"content": {"application/json": {"examples": ASK_EXAMPLES}}},
        422: VALIDATION_ERROR_EXAMPLE,
        503: DATABASE_UNAVAILABLE,
    },
)
def ask(
    body: AskRequest,
    settings: SettingsDep,
    engine: EngineDep,
    embedder: EmbedderDep,
    llm: LLMDep,
) -> AskResponse:
    answer = answer_question(
        body.question,
        engine=engine,
        embedder=embedder,
        llm=llm,
        top_k=settings.retrieval_top_k,
        min_similarity=settings.min_similarity,
    )
    # Not the question itself: users may type personal details into it.
    logger.info(
        "ask.answered",
        extra={
            "mode": answer.reply.mode,
            "fallback_reason": answer.reply.fallback_reason,
            "top_similarity": answer.top_similarity,
            "citations": len(answer.reply.citations),
            "retrieval_ms": answer.retrieval_ms,
            "generation_ms": answer.reply.generation_ms,
            "total_ms": answer.total_ms,
        },
    )
    # Questions aren't stored in the database yet, so these IDs only link logs and feedback.
    return AskResponse.from_answer(
        answer,
        message_id=uuid.uuid4(),
        conversation_id=body.conversation_id or uuid.uuid4(),
    )
