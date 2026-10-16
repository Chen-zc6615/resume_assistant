from __future__ import annotations

from openai import OpenAI

from knowledge_service.core.config import Settings


class EmbeddingClient:
    def __init__(self, settings: Settings):
        self.model = settings.embedding_model
        self.client = OpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url.rstrip("/"),
            timeout=settings.model_timeout_seconds,
            max_retries=0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=texts)
        data = sorted(response.data, key=lambda item: item.index)
        vectors = [item.embedding for item in data]
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding 返回数量错误：请求 {len(texts)} 条，返回 {len(vectors)} 条"
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

