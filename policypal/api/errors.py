"""Every error the API returns, defined once.

Code raises these (`raise DOCUMENT_NOT_FOUND.exception()`), and routes list them in
Swagger (`responses=documented(DOCUMENT_NOT_FOUND)`), so the docs show exactly what the
API sends. tests/integration/test_documented_errors.py checks that they match.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel

from policypal.ingest import uploads


class ErrorResponse(BaseModel):
    """Errors have a plain message in `detail` (validation errors list each problem)."""

    detail: str


@dataclass(frozen=True)
class ApiError:
    status_code: int
    detail: str  # the message the client receives
    description: str  # when it happens (shown in Swagger)

    def exception(self) -> HTTPException:
        return HTTPException(self.status_code, self.detail)


DATABASE_UNAVAILABLE = ApiError(
    status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable.", "The database can't be reached."
)
DOCUMENT_NOT_FOUND = ApiError(
    status.HTTP_404_NOT_FOUND, "Document not found.", "No document has this id."
)
ADMIN_DISABLED = ApiError(
    status.HTTP_503_SERVICE_UNAVAILABLE,
    "Admin features are disabled: set ADMIN_TOKEN.",
    "Admin features are off because ADMIN_TOKEN is not set.",
)
ADMIN_TOKEN_MISSING = ApiError(
    status.HTTP_401_UNAUTHORIZED,
    "Admin token required in the X-Admin-Token header.",
    "The X-Admin-Token header is missing.",
)
ADMIN_TOKEN_WRONG = ApiError(
    status.HTTP_403_FORBIDDEN, "Admin token is not valid.", "The admin token is wrong."
)

# Upload rejections carry their own message. These examples use the same wording.
UPLOAD_ERRORS = (
    ApiError(
        status.HTTP_409_CONFLICT,
        uploads.NAME_TAKEN.format(slug="leave-guide"),
        "An uploaded policy with this name has different content (use replace=true).",
    ),
    ApiError(
        status.HTTP_409_CONFLICT,
        uploads.SAMPLE_NAME.format(slug="leave-policy"),
        "The name belongs to a built-in sample policy.",
    ),
    ApiError(
        status.HTTP_413_CONTENT_TOO_LARGE,
        uploads.TOO_LARGE.format(max_mb=5),
        "The file is larger than MAX_UPLOAD_MB.",
    ),
    ApiError(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, uploads.UNSUPPORTED_TYPE, "Not a .md or .pdf file."
    ),
    ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        uploads.NOT_A_PDF,
        "The file can't be read as a policy (e.g. not a real PDF, or a scanned PDF).",
    ),
)
ADMIN_ERRORS = (ADMIN_TOKEN_MISSING, ADMIN_TOKEN_WRONG, ADMIN_DISABLED, DATABASE_UNAVAILABLE)


def documented(*errors: ApiError) -> dict[int | str, dict[str, Any]]:
    """`responses=` entries for a route, so Swagger lists each error and its message.

    Errors that share a status code become named examples of one response.
    """
    by_status: dict[int, list[ApiError]] = {}
    for error in errors:
        by_status.setdefault(error.status_code, []).append(error)
    return {
        status_code: {
            "model": ErrorResponse,
            "description": " Or: ".join(error.description for error in group),
            "content": {
                "application/json": {
                    "examples": {
                        error.description: {"value": {"detail": error.detail}} for error in group
                    }
                }
            },
        }
        for status_code, group in by_status.items()
    }


def validation_error(
    location: list[str], message: str, value: Any, kind: str, **ctx: Any
) -> dict[str, Any]:
    """A 422 `responses=` entry showing one problem, exactly as FastAPI reports it."""
    problem: dict[str, Any] = {"type": kind, "loc": location, "msg": message, "input": value}
    if ctx:
        problem["ctx"] = ctx
    return {
        "description": "The request is invalid.",
        "content": {"application/json": {"example": {"detail": [problem]}}},
    }
