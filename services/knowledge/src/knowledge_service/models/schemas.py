from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentType = Literal["talent_profile", "job_doc", "policy", "other"]


class DocumentUpsert(BaseModel):
    document_type: DocumentType
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentWriteResponse(BaseModel):
    document_id: str
    chunk_count: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    document_types: list[DocumentType] | None = None
    metadata_filter: dict[str, Any] | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_type: str
    content: str
    metadata: dict[str, Any]
    rerank_score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    latency_ms: float


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    section: str
    snippet: str
    relevance_score: float


class ChatResponse(BaseModel):
    query: str
    answer: str
    is_refused: bool
    citations: list[Citation] = Field(default_factory=list)
    latency_ms: float

