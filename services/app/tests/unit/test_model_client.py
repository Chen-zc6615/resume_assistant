from types import SimpleNamespace

from app_service.clients import model_client


def test_extract_json_uses_normalization_model(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"name":"张三"}'))]
        )

    settings = SimpleNamespace(
        dashscope_api_key="test-key",
        llm_base_url="https://example.test/v1/",
        normalization_model="qwen-plus",
        normalization_timeout_seconds=20.0,
    )
    monkeypatch.setattr(model_client, "get_settings", lambda: settings)
    monkeypatch.setattr(model_client, "litellm_completion", fake_completion)

    result = model_client.extract_json("只输出 JSON", "张三的简历")

    assert result == '{"name":"张三"}'
    assert captured["model"] == "openai/qwen-plus"
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["num_retries"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"] == [
        {"role": "system", "content": "只输出 JSON"},
        {"role": "user", "content": "张三的简历"},
    ]


def test_complete_agent_uses_agent_model(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[])

    settings = SimpleNamespace(
        dashscope_api_key="test-key",
        llm_base_url="https://example.test/v1/",
        agent_model="qwen-max",
        agent_timeout_seconds=45.0,
    )
    monkeypatch.setattr(model_client, "get_settings", lambda: settings)
    monkeypatch.setattr(model_client, "litellm_completion", fake_completion)

    model_client.complete_agent(messages=[])

    assert captured["model"] == "openai/qwen-max"
    assert captured["timeout"] == 45.0
    assert captured["num_retries"] == 0
