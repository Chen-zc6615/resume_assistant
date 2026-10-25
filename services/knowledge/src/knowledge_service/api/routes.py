from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from knowledge_service.models.schemas import (
    DocumentUpsert,
    DocumentWriteResponse,
    SearchRequest,
    SearchResponse,
    TalentProfileUpsert,
)
from knowledge_service.services.knowledge import KnowledgeService

router = APIRouter()


def service_from(request: Request) -> KnowledgeService:
    return request.app.state.knowledge_service


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    service = service_from(request)
    return {
        "status": "healthy",
        "embedding_model": service.settings.embedding_model,
        "rerank_model": service.settings.rerank_model,
        "indexed_chunks": service.store.collection.count(),
    }


@router.put("/api/v1/documents/{document_id}", response_model=DocumentWriteResponse)
def upsert_document(
    document_id: str, document: DocumentUpsert, request: Request
) -> DocumentWriteResponse:
    return service_from(request).upsert(document_id, document)


@router.put("/api/v1/talent-profiles/{document_id}", response_model=DocumentWriteResponse)
def upsert_talent_profile(
    document_id: str, profile: TalentProfileUpsert, request: Request
) -> DocumentWriteResponse:
    return service_from(request).upsert_talent_profile(document_id, profile)


@router.delete("/api/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, request: Request) -> Response:
    service_from(request).delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request) -> SearchResponse:
    return service_from(request).search(body)

