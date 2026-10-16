from __future__ import annotations

import time
from typing import Any

import jieba
from rank_bm25 import BM25Okapi

from knowledge_service.core.config import Settings
from knowledge_service.models.schemas import SearchResult
from knowledge_service.services.embedding import EmbeddingClient
from knowledge_service.services.reranker import RerankerClient
from knowledge_service.services.vector_store import VectorStore


def tokenize(text: str) -> list[str]:
    return [token.strip().lower() for token in jieba.cut(text) if token.strip()]


def build_where(
    document_types: list[str] | None,
    metadata_filter: dict[str, Any] | None,
) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    if document_types:
        conditions.append({"document_type": {"$in": document_types}})
    for key, value in (metadata_filter or {}).items():
        conditions.append({key: value})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def metadata_matches(
    metadata: dict[str, Any],
    document_types: list[str] | None,
    metadata_filter: dict[str, Any] | None,
) -> bool:
    if document_types and metadata.get("document_type") not in document_types:
        return False
    return all(metadata.get(key) == value for key, value in (metadata_filter or {}).items())


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
        document_types: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> tuple[list[SearchResult], float]:
        started = time.perf_counter()
        final_top_k = top_k or self.settings.knowledge_final_top_k
        rough_top_k = max(self.settings.knowledge_rough_top_k, final_top_k)
        all_chunks = [
            chunk
            for chunk in self.store.all_chunks()
            if metadata_matches(chunk["metadata"], document_types, metadata_filter)
        ]
        if not all_chunks:
            return [], round((time.perf_counter() - started) * 1000, 2)

        tokenized = [tokenize(chunk["content"]) for chunk in all_chunks]
        bm25 = BM25Okapi(tokenized)
        bm25_scores = bm25.get_scores(tokenize(query))
        bm25_order = sorted(
            range(len(all_chunks)), key=lambda index: bm25_scores[index], reverse=True
        )[:rough_top_k]

        where = build_where(document_types, metadata_filter)
        dense = self.store.dense_search(
            self.embeddings.embed_query(query), rough_top_k, where
        )

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
        )[:final_top_k]
        results = [
            SearchResult(
                chunk_id=chunk["chunk_id"],
                document_id=str(chunk["metadata"]["document_id"]),
                document_type=str(chunk["metadata"]["document_type"]),
                content=chunk["content"],
                metadata=chunk["metadata"],
                rerank_score=round(float(score), 6),
            )
            for chunk, score in ranked
        ]
        return results, round((time.perf_counter() - started) * 1000, 2)

