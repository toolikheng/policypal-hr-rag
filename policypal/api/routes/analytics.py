from typing import Annotated

from fastapi import APIRouter, Depends, Query

from policypal.analytics import summarize
from policypal.api.deps import EngineDep, require_admin
from policypal.api.errors import ADMIN_ERRORS, documented, validation_error
from policypal.api.schemas import AnalyticsResponse

router = APIRouter(tags=["analytics"])


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Question, refusal, feedback and latency figures for a period (admin)",
    description="Computed from the stored questions. Rates are null, not 0, when there is "
    "nothing to divide by.",
    dependencies=[Depends(require_admin)],
    responses={
        **documented(*ADMIN_ERRORS),
        422: validation_error(
            ["query", "days"],
            "Input should be greater than or equal to 1",
            "0",
            "greater_than_equal",
            ge=1,
        ),
    },
)
def analytics(
    engine: EngineDep,
    days: Annotated[int, Query(ge=1, le=365, description="How many days back to look.")] = 30,
) -> AnalyticsResponse:
    return AnalyticsResponse.model_validate(summarize(engine, days), from_attributes=True)
