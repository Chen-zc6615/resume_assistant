from types import SimpleNamespace

from knowledge_service.clients import reranker_client as reranker_module
from knowledge_service.clients.reranker_client import RerankerClient


def test_score_uses_litellm_dashscope_provider_and_restores_order(monkeypatch):
    captured = {}

    def fake_rerank(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            results=[
                {"index": 1, "relevance_score": 0.25},
                {"index": 0, "relevance_score": 0.9},
            ]
        )

    monkeypatch.setattr(reranker_module, "litellm_rerank", fake_rerank)
    settings = SimpleNamespace(
        rerank_model="qwen3-reranker-8b",
        model_api_key="test-key",
        model_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        rerank_timeout_seconds=30.0,
    )
    client = RerankerClient(settings)
    documents = ["Python 后端工程师", "Java 后端工程师"]

    scores = client.score("熟悉 Python 的候选人", documents)

    assert scores == [0.9, 0.25]
    assert captured == {
        "model": "qwen3-reranker-8b",
        "query": "熟悉 Python 的候选人",
        "documents": documents,
        "custom_llm_provider": "dashscope",
        "top_n": 2,
        "return_documents": False,
        "api_key": "test-key",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "timeout": 30.0,
        "num_retries": 0,
    }
