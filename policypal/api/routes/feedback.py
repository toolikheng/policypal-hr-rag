import logging

from fastapi import APIRouter

from policypal.api.deps import EngineDep
from policypal.api.errors import (
    DATABASE_UNAVAILABLE,
    MESSAGE_NOT_FOUND,
    documented,
    validation_error,
)
from policypal.api.schemas import FeedbackRequest, FeedbackResponse
from policypal.history import record_feedback

logger = logging.getLogger("policypal.api")

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Vote on an answer (thumbs up or down, optional comment)",
    description="Stores one vote per answer. Voting again replaces the rating and comment.",
    responses={
        **documented(MESSAGE_NOT_FOUND),
        422: validation_error(
            ["body", "rating"],
            "Input should be 'up' or 'down'",
            "meh",
            "literal_error",
            expected="'up' or 'down'",
        ),
        **documented(DATABASE_UNAVAILABLE),
    },
)
def feedback(body: FeedbackRequest, engine: EngineDep) -> FeedbackResponse:
    if not record_feedback(engine, body.message_id, body.rating, body.comment):
        raise MESSAGE_NOT_FOUND.exception()
    # The comment itself isn't logged: users may type personal details into it.
    logger.info(
        "feedback.recorded",
        extra={
            "message_id": str(body.message_id),
            "rating": body.rating,
            "comment_chars": len(body.comment or ""),
        },
    )
    return FeedbackResponse(status="recorded")
