from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse

from policypal import catalogue
from policypal.api.deps import EmbedderDep, EngineDep, SettingsDep, require_admin
from policypal.api.errors import (
    ADMIN_ERRORS,
    DATABASE_UNAVAILABLE,
    DOCUMENT_NOT_FOUND,
    UPLOAD_ERRORS,
    ConflictResponse,
    documented,
    validation_error,
)
from policypal.api.schemas import (
    DOCUMENT_SUMMARY_EXAMPLE,
    UPLOAD_EXAMPLE,
    DocumentDetail,
    DocumentSummary,
    IngestResultResponse,
    ReingestResponse,
    UploadResponse,
)
from policypal.ingest.uploads import (
    FileTooLarge,
    InvalidUpload,
    UnsupportedFileType,
    UploadConflict,
    add_upload,
    rescan,
)

router = APIRouter(tags=["documents"])


@router.get(
    "/documents",
    response_model=list[DocumentSummary],
    summary="List the policies that can be searched",
    responses={
        200: {"content": {"application/json": {"example": [DOCUMENT_SUMMARY_EXAMPLE]}}},
        **documented(DATABASE_UNAVAILABLE),
    },
)
def list_documents(engine: EngineDep) -> list[DocumentSummary]:
    return [
        DocumentSummary.model_validate(document, from_attributes=True)
        for document in catalogue.list_documents(engine)
    ]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    summary="Show one policy, section by section (the source viewer)",
    responses={
        **documented(DOCUMENT_NOT_FOUND, DATABASE_UNAVAILABLE),
        422: validation_error(
            ["path", "document_id"],
            "Input should be a valid integer, unable to parse string as an integer",
            "leave-policy",
            "int_parsing",
        ),
    },
)
def get_document(document_id: int, engine: EngineDep) -> DocumentDetail:
    document = catalogue.get_document(engine, document_id)
    if document is None:
        raise DOCUMENT_NOT_FOUND.exception()
    return DocumentDetail.model_validate(document, from_attributes=True)


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
    summary="Upload a new policy (.md or .pdf) and make it searchable (admin)",
    description=(
        "A policy is identified by its file name (its slug, e.g. `leave-policy`). Uploading "
        "the same bytes again changes nothing. Different content for an existing name is "
        "refused with 409 unless `replace=true`. Built-in sample policies can never be "
        "replaced by upload."
    ),
    dependencies=[Depends(require_admin)],
    responses={
        201: {"content": {"application/json": {"example": UPLOAD_EXAMPLE}}},
        200: {
            "model": UploadResponse,
            "description": "The policy already existed: unchanged, or updated with replace=true.",
            "content": {"application/json": {"example": {**UPLOAD_EXAMPLE, "status": "updated"}}},
        },
        **documented(*ADMIN_ERRORS, *UPLOAD_ERRORS),
    },
)
def upload_document(
    file: Annotated[UploadFile, File(description="The policy file: .md (UTF-8) or .pdf.")],
    response: Response,
    settings: SettingsDep,
    engine: EngineDep,
    embedder: EmbedderDep,
    replace: Annotated[
        bool,
        Query(description="Replace an uploaded policy with the same name (never a sample)."),
    ] = False,
) -> UploadResponse | JSONResponse:
    try:
        result = add_upload(
            engine,
            embedder,
            settings.upload_dir,
            file.filename or "",
            file.file,
            replace=replace,
            max_mb=settings.max_upload_mb,
        )
    except FileTooLarge as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except InvalidUpload as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except UploadConflict as exc:
        body = ConflictResponse(detail=str(exc), conflict=exc.conflict)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())

    if result.status != "created":
        response.status_code = status.HTTP_200_OK
    return UploadResponse.model_validate(result, from_attributes=True)


@router.post(
    "/documents/reingest",
    response_model=ReingestResponse,
    summary="Re-scan the sample and upload folders (admin)",
    description="Safe to run any number of times: unchanged files are skipped, nothing is "
    "duplicated, and documents whose file is gone are removed.",
    dependencies=[Depends(require_admin)],
    responses=documented(*ADMIN_ERRORS),
)
def reingest(settings: SettingsDep, engine: EngineDep, embedder: EmbedderDep) -> ReingestResponse:
    results = rescan(engine, embedder, settings.upload_dir)
    return ReingestResponse(
        results=[IngestResultResponse.model_validate(r, from_attributes=True) for r in results]
    )
