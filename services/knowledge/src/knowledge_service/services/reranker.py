from __future__ import annotations

import httpx

from knowledge_service.core.config import Settings

# DashScope 官方未提供 OpenAI 兼容的 /rerank，只有原生接口
_DASHSCOPE_NATIVE_RERANK_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


class RerankerClient:
    def __init__(self, settings: Settings):
        self.model = settings.rerank_model
        self.api_key = settings.model_api_key
        self.timeout = settings.model_timeout_seconds
        self.native_dashscope = "dashscope.aliyuncs.com" in settings.model_base_url
        if self.native_dashscope:
            self.url = _DASHSCOPE_NATIVE_RERANK_URL
        else:
            self.url = f"{settings.model_base_url.rstrip('/')}/rerank"

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if self.native_dashscope:
            body = {
                "model": self.model,
                "input": {"query": query, "documents": documents},
                "top_n": len(documents),
            }
        else:
            body = {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            }
        response = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
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

