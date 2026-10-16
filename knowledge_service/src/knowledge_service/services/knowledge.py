from __future__ import annotations

import re

from knowledge_service.core.config import Settings
from knowledge_service.models.schemas import (
    ChatResponse,
    Citation,
    DocumentUpsert,
    DocumentWriteResponse,
    SearchRequest,
    SearchResponse,
)
from knowledge_service.services.chunker import MarkdownChunker
from knowledge_service.services.embedding import EmbeddingClient
from knowledge_service.services.reranker import RerankerClient
from knowledge_service.services.retriever import HybridRetriever
from knowledge_service.services.vector_store import VectorStore


class KnowledgeService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunker = MarkdownChunker(
            chunk_size=settings.knowledge_chunk_size,
            chunk_overlap=settings.knowledge_chunk_overlap,
        )
        embeddings = EmbeddingClient(settings)
        store = VectorStore(settings, embeddings)
        self.store = store
        self.retriever = HybridRetriever(
            settings=settings,
            store=store,
            embeddings=embeddings,
            reranker=RerankerClient(settings),
        )

    def upsert(self, document_id: str, document: DocumentUpsert) -> DocumentWriteResponse:
        chunks = self.chunker.split(
            document_id=document_id,
            document_type=document.document_type,
            content=document.content,
            metadata=document.metadata,
        )
        count = self.store.upsert_document(document_id, chunks)
        return DocumentWriteResponse(document_id=document_id, chunk_count=count)

    def delete(self, document_id: str) -> None:
        self.store.delete_document(document_id)

    def search(self, request: SearchRequest) -> SearchResponse:
        results, latency = self.retriever.search(
            query=request.query,
            document_types=request.document_types,
            metadata_filter=request.metadata_filter,
            top_k=request.top_k,
        )
        return SearchResponse(query=request.query, results=results, latency_ms=latency)

    def chat(self, request: SearchRequest) -> ChatResponse:
        search_response = self.search(request)
        results = search_response.results
        if not results or results[0].rerank_score < self.settings.knowledge_refusal_threshold:
            return ChatResponse(
                query=request.query,
                answer="抱歉，知识库中没有找到足够可靠的相关内容。",
                is_refused=True,
                citations=[],
                latency_ms=search_response.latency_ms,
            )

        citations = [
            Citation(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                section=str(result.metadata.get("section", "正文")),
                snippet=result.content[:120],
                relevance_score=result.rerank_score,
            )
            for result in results
        ]
        top = results[0]
        text = re.sub(r"\s+", " ", top.content).strip()
        answer = (
            f"根据知识库检索结果：{text[:500]} "
            f"[来源: {top.document_id} - {top.metadata.get('section', '正文')}]"
        )
        return ChatResponse(
            query=request.query,
            answer=answer,
            is_refused=False,
            citations=citations,
            latency_ms=search_response.latency_ms,
        )

