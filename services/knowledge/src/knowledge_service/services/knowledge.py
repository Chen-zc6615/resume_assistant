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
    SearchResult,
    TalentProfileUpsert,
)
from knowledge_service.services.chunker import MarkdownChunker
from knowledge_service.services.embedding import EmbeddingClient
from knowledge_service.services.reranker import RerankerClient
from knowledge_service.services.retriever import HybridRetriever, RetrievalDiagnostics
from knowledge_service.services.vector_store import VectorStore
from knowledge_service.services.wiki_card import build_talent_wiki_card


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

    def upsert_talent_profile(
        self, document_id: str, profile: TalentProfileUpsert
    ) -> DocumentWriteResponse:
        card = build_talent_wiki_card(document_id, profile)
        return self.upsert(
            document_id,
            DocumentUpsert(
                document_type="talent_profile",
                content=card.content,
                metadata=card.metadata,
            ),
        )

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
        response, _ = self.chat_with_diagnostics(request)
        return response

    def chat_with_diagnostics(
        self, request: SearchRequest
    ) -> tuple[ChatResponse, RetrievalDiagnostics]:
        outcome = self.retriever.search_with_diagnostics(
            query=request.query,
            document_types=request.document_types,
            metadata_filter=request.metadata_filter,
            top_k=request.top_k,
        )
        response = self._build_chat_response(
            query=request.query,
            results=outcome.results,
            latency_ms=outcome.latency_ms,
        )
        return response, outcome.diagnostics

    def _build_chat_response(
        self,
        query: str,
        results: list[SearchResult],
        latency_ms: float,
    ) -> ChatResponse:
        if not results or results[0].rerank_score < self.settings.knowledge_refusal_threshold:
            return ChatResponse(
                query=query,
                answer="抱歉，知识库中没有找到足够可靠的相关内容。",
                is_refused=True,
                citations=[],
                latency_ms=latency_ms,
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
            query=query,
            answer=answer,
            is_refused=False,
            citations=citations,
            latency_ms=latency_ms,
        )
