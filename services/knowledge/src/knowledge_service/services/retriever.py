from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jieba
from rank_bm25 import BM25Okapi

from knowledge_service.clients.embedding_client import EmbeddingClient
from knowledge_service.clients.reranker_client import RerankerClient
from knowledge_service.core.config import Settings
from knowledge_service.models.schemas import SearchResult
from knowledge_service.services.vector_store import VectorStore


@dataclass(frozen=True)
class RetrievalDiagnostics:
    """一次检索在各阶段产生的有序切片 ID。"""

    bm25_chunk_ids: list[str]
    dense_chunk_ids: list[str]
    rrf_chunk_ids: list[str]
    reranked_chunk_ids: list[str]
    reranked_scores: list[float]


@dataclass(frozen=True)
class RetrievalOutcome:
    """带中间诊断数据的完整检索结果。"""

    results: list[SearchResult]
    latency_ms: float
    diagnostics: RetrievalDiagnostics


def tokenize(text: str) -> list[str]:
    return [token.strip().lower() for token in jieba.cut(text) if token.strip()]


class HybridRetriever:
    def __init__(
        self,
        settings: Settings,
        store: VectorStore,
        embeddings: EmbeddingClient,
        reranker: RerankerClient,
    ):
        self.settings = settings
        self.store = store
        self.embeddings = embeddings
        self.reranker = reranker

    def search(
        self,
        query: str,
    ) -> tuple[list[SearchResult], float]:
        """执行线上检索，保持原有返回契约不变。"""
        outcome = self.search_with_diagnostics(query=query)
        return outcome.results, outcome.latency_ms

    def search_with_diagnostics(
        self,
        query: str,
    ) -> RetrievalOutcome:
        """执行检索并返回 BM25、Dense、RRF 与 Rerank 的完整排序轨迹。"""
        started = time.perf_counter()
        final_top_k = self.settings.knowledge_final_top_k
        rough_top_k = max(self.settings.knowledge_rough_top_k, final_top_k)
        all_chunks = self.store.all_chunks()
        if not all_chunks:
            return RetrievalOutcome(
                results=[],
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                diagnostics=RetrievalDiagnostics(
                    bm25_chunk_ids=[],
                    dense_chunk_ids=[],
                    rrf_chunk_ids=[],
                    reranked_chunk_ids=[],
                    reranked_scores=[],
                ),
            )

        tokenized = [tokenize(chunk["content"]) for chunk in all_chunks]
        bm25 = BM25Okapi(tokenized)
        bm25_scores = bm25.get_scores(tokenize(query))
        bm25_order = sorted(
            range(len(all_chunks)), key=lambda index: bm25_scores[index], reverse=True
        )[:rough_top_k]

        dense = self.store.dense_search(self.embeddings.embed_query(query), rough_top_k)

        candidates: dict[str, dict[str, Any]] = {}
        rrf_scores: dict[str, float] = {}
        for rank, index in enumerate(bm25_order, 1):
            chunk = all_chunks[index]
            chunk_id = chunk["chunk_id"]
            candidates[chunk_id] = chunk
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1 / (60 + rank)
        for rank, chunk in enumerate(dense, 1):
            chunk_id = chunk["chunk_id"]
            candidates[chunk_id] = chunk
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1 / (60 + rank)

        candidate_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:rough_top_k]
        candidate_chunks = [candidates[chunk_id] for chunk_id in candidate_ids]
        rerank_scores = self.reranker.score(
            query, [chunk["content"] for chunk in candidate_chunks]
        )

        ranked = sorted(
            zip(candidate_chunks, rerank_scores), key=lambda item: item[1], reverse=True
        )
        results = [
            SearchResult(
                chunk_id=chunk["chunk_id"],
                talent_card_id=str(chunk["metadata"]["talent_card_id"]),
                document_type=str(chunk["metadata"]["document_type"]),
                content=chunk["content"],
                metadata=chunk["metadata"],
                rerank_score=round(float(score), 6),
            )
            for chunk, score in ranked[:final_top_k]
        ]
        return RetrievalOutcome(
            results=results,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            diagnostics=RetrievalDiagnostics(
                bm25_chunk_ids=[all_chunks[index]["chunk_id"] for index in bm25_order],
                dense_chunk_ids=[chunk["chunk_id"] for chunk in dense],
                rrf_chunk_ids=candidate_ids,
                reranked_chunk_ids=[chunk["chunk_id"] for chunk, _ in ranked],
                reranked_scores=[round(float(score), 6) for _, score in ranked],
            ),
        )

