import logging

from fastapi import APIRouter

from policypal.answering import answer_question
from policypal.api.deps import EmbedderDep, EngineDep, LLMDep, SettingsDep
from policypal.api.errors import DATABASE_UNAVAILABLE, documented, validation_error
from policypal.api.schemas import ASK_EXAMPLES, AskRequest, AskResponse
from policypal.history import save_answer

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
        "(`mode` = extractive, with a `fallback_reason`). The question, answer and sources "
        "are saved for analytics; use the returned `message_id` to vote on the answer."
    ),
    responses={
        200: {"content": {"application/json": {"examples": ASK_EXAMPLES}}},
        422: validation_error(
            ["body", "question"],
            "String should have at least 3 characters",
            "hi",
            "string_too_short",
            min_length=3,
        ),
        **documented(DATABASE_UNAVAILABLE),
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
    # The LLM call is over before the transaction starts, so no connection is held
    # while waiting for it.
    saved = save_answer(
        engine,
        body.question,
        answer,
        conversation_id=body.conversation_id,
        channel=body.channel,
    )
    # Not the question itself: users may type personal details into it.
    logger.info(
        "ask.answered",
        extra={
            "message_id": str(saved.message_id),
            "mode": answer.reply.mode,
            "fallback_reason": answer.reply.fallback_reason,
            "top_similarity": answer.top_similarity,
            "citations": len(answer.reply.citations),
            "retrieval_ms": answer.retrieval_ms,
            "generation_ms": answer.reply.generation_ms,
            "total_ms": answer.total_ms,
        },
    )
    return AskResponse.from_answer(
        answer, message_id=saved.message_id, conversation_id=saved.conversation_id
    )
