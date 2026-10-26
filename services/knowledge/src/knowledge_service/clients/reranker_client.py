"""Rerank 模型客户端。"""

from __future__ import annotations

from litellm import rerank as litellm_rerank

from knowledge_service.core.config import Settings


class RerankerClient:
    def __init__(self, settings: Settings):
        self.model = settings.rerank_model
        self.api_key = settings.model_api_key
        self.timeout = settings.rerank_timeout_seconds
        self.api_base = settings.model_base_url.rstrip("/")
        if "/" in self.model:
            self.provider = None
        elif "dashscope.aliyuncs.com" in self.api_base:
            self.provider = "dashscope"
        else:
            self.provider = "litellm_proxy"

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        response = litellm_rerank(
            model=self.model,
            query=query,
            documents=documents,
            custom_llm_provider=self.provider,
            top_n=len(documents),
            return_documents=False,
            api_key=self.api_key,
            api_base=self.api_base,
            timeout=self.timeout,
            num_retries=0,
        )
        results = response.results or []
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
