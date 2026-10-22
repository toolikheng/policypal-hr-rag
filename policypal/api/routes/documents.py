from itertools import groupby

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from policypal.api.deps import EngineDep
from policypal.api.schemas import (
    DATABASE_UNAVAILABLE,
    DOCUMENT_SUMMARY_EXAMPLE,
    ChunkText,
    DocumentDetail,
    DocumentSummary,
    SectionResponse,
    error_example,
    validation_error_example,
)
from policypal.models import Document, DocumentChunk

router = APIRouter(tags=["documents"])


@router.get(
    "/documents",
    response_model=list[DocumentSummary],
    summary="List the policies that can be searched",
    responses={
        200: {"content": {"application/json": {"example": [DOCUMENT_SUMMARY_EXAMPLE]}}},
        503: DATABASE_UNAVAILABLE,
    },
)
def list_documents(engine: EngineDep) -> list[DocumentSummary]:
    chunk_count = func.count(DocumentChunk.id)
    query = (
        select(Document, chunk_count)
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .group_by(Document.id)
        .order_by(Document.title, Document.id)
    )
    with Session(engine) as session:
        return [_summary(document, chunks) for document, chunks in session.execute(query)]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    summary="Show one policy, section by section (the source viewer)",
    responses={
        404: error_example("No document has this id.", "Document not found."),
        422: validation_error_example(
            ["path", "document_id"], "Input should be a valid integer", "leave-policy"
        ),
        503: DATABASE_UNAVAILABLE,
    },
)
def get_document(document_id: int, engine: EngineDep) -> DocumentDetail:
    with Session(engine) as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.section,
                DocumentChunk.section_path,
                DocumentChunk.content,
            )
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = session.execute(query).all()
        # A long section is split into several chunks, which are next to each other.
        sections = [
            SectionResponse(
                section=section,
                section_path=section_path,
                chunks=[ChunkText(id=chunk.id, text=chunk.content) for chunk in group],
            )
            for (section, section_path), group in groupby(
                chunks, key=lambda chunk: (chunk.section, chunk.section_path)
            )
        ]
        return DocumentDetail(**_summary(document, len(chunks)).model_dump(), sections=sections)


def _summary(document: Document, chunks: int) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        slug=document.slug,
        title=document.title,
        file_type=document.file_type,
        origin=document.origin,
        chunks=chunks,
        updated_at=document.updated_at,
    )
