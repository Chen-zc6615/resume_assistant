from types import SimpleNamespace

from knowledge_service.clients import embedding_client as embedding_module
from knowledge_service.clients.embedding_client import EmbeddingClient


def test_embed_batches_inputs_and_preserves_response_order(monkeypatch):
    calls = []

    def fake_embedding(**kwargs):
        calls.append(kwargs)
        offset = sum(len(call["input"]) for call in calls[:-1])
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(offset + index)])
                for index in reversed(range(len(kwargs["input"])))
            ]
        )

    monkeypatch.setattr(embedding_module, "litellm_embedding", fake_embedding)
    settings = SimpleNamespace(
        embedding_model="test-embedding-model",
        model_api_key="test-key",
        model_base_url="https://example.test/v1/",
        embedding_timeout_seconds=30.0,
    )
    client = EmbeddingClient(settings)
    texts = [f"text-{index}" for index in range(12)]

    vectors = client.embed(texts)

    assert vectors == [[float(index)] for index in range(12)]
    assert [call["input"] for call in calls] == [texts[:10], texts[10:]]
    assert all(call["model"] == "openai/test-embedding-model" for call in calls)
    assert all(call["api_base"] == "https://example.test/v1" for call in calls)
