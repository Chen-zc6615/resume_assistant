from __future__ import annotations

import httpx

from knowledge_service.core.config import Settings


class RerankerClient:
    def __init__(self, settings: Settings):
        self.model = settings.rerank_model
        self.url = f"{settings.model_base_url.rstrip('/')}/rerank"
        self.api_key = settings.model_api_key
        self.timeout = settings.model_timeout_seconds

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        response = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if results is None:
            results = payload["output"]["results"]
        scores = {
            int(item["index"]): float(item["relevance_score"])
            for item in results
        }
        expected = set(range(len(documents)))
        if set(scores) != expected:
            raise RuntimeError(
                f"Rerank 返回结果不完整：请求 {sorted(expected)}，返回 {sorted(scores)}"
            )
        return [scores[index] for index in range(len(documents))]

