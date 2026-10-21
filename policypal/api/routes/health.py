from fastapi import APIRouter, Request, Response, status

from policypal import __version__
from policypal.api.schemas import HealthResponse
from policypal.db import check_database

router = APIRouter(tags=["health"])

UNAVAILABLE_EXAMPLE = {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check that the API and its database are working",
    responses={
        503: {
            "model": HealthResponse,
            "description": "The database is unreachable or not migrated.",
            "content": {"application/json": {"example": UNAVAILABLE_EXAMPLE}},
        }
    },
)
def health(request: Request, response: Response) -> HealthResponse:
    database = check_database(request.app.state.engine)
    if database != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if database == "ok" else "unavailable",
        database=database,
        version=__version__,
    )
