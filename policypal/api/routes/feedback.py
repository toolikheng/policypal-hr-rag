import logging

from fastapi import APIRouter, status

from policypal.api.errors import validation_error
from policypal.api.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger("policypal.api")

router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FeedbackResponse,
    summary="Vote on an answer (thumbs up or down, optional comment)",
    description="The vote is checked and logged. Storing it in the database comes later, "
    "behind the same request.",
    responses={
        422: validation_error(
            ["body", "rating"],
            "Input should be 'up' or 'down'",
            "meh",
            "literal_error",
            expected="'up' or 'down'",
        )
    },
)
def feedback(body: FeedbackRequest) -> FeedbackResponse:
    # The comment itself isn't logged: users may type personal details into it.
    logger.info(
        "feedback.received",
        extra={
            "message_id": str(body.message_id),
            "rating": body.rating,
            "comment_chars": len(body.comment or ""),
        },
    )
    return FeedbackResponse(status="accepted")
