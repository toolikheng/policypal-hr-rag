from fastapi import APIRouter, Request, Response, status

from policypal import __version__
from policypal.api.schemas import HealthResponse
from policypal.db import check_database

router = APIRouter(tags=["health"])

UNAVAILABLE_EXAMPLE = {
    "status": "unavailable",
    "database": "unreachable",
    "documents": None,
    "chunks": None,
    "version": "0.1.0",
}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check that the API and its database are working",
    responses={
        503: {
            "model": HealthResponse,
            "description": "The database is unreachable or not at the newest migration.",
            "content": {"application/json": {"example": UNAVAILABLE_EXAMPLE}},
        }
    },
)
def health(request: Request, response: Response) -> HealthResponse:
    check = check_database(request.app.state.engine)
    report = HealthResponse(
        database=check.status, documents=check.documents, chunks=check.chunks, version=__version__
    )
    if report.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
