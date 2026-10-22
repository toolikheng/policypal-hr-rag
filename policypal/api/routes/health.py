from fastapi import APIRouter, Response, status

from policypal import __version__
from policypal.api.deps import EngineDep, LLMDep
from policypal.api.schemas import HealthResponse, LLMHealth
from policypal.db import check_database
from policypal.llm import describe_llm

router = APIRouter(tags=["health"])

UNAVAILABLE_EXAMPLE = {
    "status": "unavailable",
    "database": "unreachable",
    "llm": {"provider": "ollama", "model": "llama3.2:3b", "status": "ok"},
    "documents": None,
    "chunks": None,
    "version": "0.1.0",
}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check that the API, its database and the LLM are working",
    description="200 with status ok, or degraded when the LLM isn't ready (answers then quote "
    "the policy text). 503 when the database can't be used.",
    responses={
        503: {
            "model": HealthResponse,
            "description": "The database is unreachable or not at the newest migration.",
            "content": {"application/json": {"example": UNAVAILABLE_EXAMPLE}},
        }
    },
)
def health(engine: EngineDep, llm: LLMDep, response: Response) -> HealthResponse:
    check = check_database(engine)
    report = HealthResponse(
        database=check.status,
        llm=LLMHealth.model_validate(describe_llm(llm), from_attributes=True),
        documents=check.documents,
        chunks=check.chunks,
        version=__version__,
    )
    if report.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
