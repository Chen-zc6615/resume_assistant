"""Embedding 模型客户端。"""

from __future__ import annotations

from litellm import embedding as litellm_embedding

from knowledge_service.core.config import Settings


class EmbeddingClient:
    # DashScope embeddings 接口单次最多 10 条输入，超限返回 InvalidParameter
    MAX_BATCH_SIZE = 10

    def __init__(self, settings: Settings):
        self.model = (
            settings.embedding_model
            if "/" in settings.embedding_model
            else f"openai/{settings.embedding_model}"
        )
        self.api_key = settings.model_api_key
        self.api_base = settings.model_base_url.rstrip("/")
        self.timeout = settings.embedding_timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[start : start + self.MAX_BATCH_SIZE]
            response = litellm_embedding(
                model=self.model,
                input=batch,
                api_key=self.api_key,
                api_base=self.api_base,
                timeout=self.timeout,
                num_retries=0,
            )
            data = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in data)
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding 返回数量错误：请求 {len(texts)} 条，返回 {len(vectors)} 条"
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
