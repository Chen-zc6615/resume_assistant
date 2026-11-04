from __future__ import annotations

from typing import Any

import chromadb

from knowledge_service.clients.embedding_client import EmbeddingClient
from knowledge_service.core.config import Settings
from knowledge_service.services.chunker import Chunk, chroma_metadata


class VectorStore:
    def __init__(self, settings: Settings, embeddings: EmbeddingClient):
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings = embeddings
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = client.get_or_create_collection(
            name="resume_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_document(self, talent_card_id: str, chunks: list[Chunk]) -> int:
        self.delete_document(talent_card_id)
        vectors = self.embeddings.embed([chunk.content for chunk in chunks])
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            metadatas=[chroma_metadata(chunk.metadata) for chunk in chunks],
            embeddings=vectors,
        )
        return len(chunks)

    def delete_document(self, talent_card_id: str) -> None:
        self.collection.delete(where={"talent_card_id": talent_card_id})

    def all_chunks(self) -> list[dict[str, Any]]:
        payload = self.collection.get(include=["documents", "metadatas"])
        return [
            {"chunk_id": chunk_id, "content": content, "metadata": metadata or {}}
            for chunk_id, content, metadata in zip(
                payload["ids"], payload["documents"] or [], payload["metadatas"] or []
            )
        ]

    def dense_search(
        self,
        query_vector: list[float],
        limit: int,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(limit, self.collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0]
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []
        return [
            {
                "chunk_id": chunk_id,
                "content": content,
                "metadata": metadata or {},
                "dense_distance": float(distance),
            }
            for chunk_id, content, metadata, distance in zip(
                ids, documents, metadatas, distances
            )
        ]

