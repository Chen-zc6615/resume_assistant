from types import SimpleNamespace

import pytest
from graph_service.clients import llm_client
from graph_service.core.config import Settings


def _settings(**overrides):
    # 所有字段都显式给值，避免测试读到本机真实的 .env
    base = dict(
        neo4j_password="test-password-123",
        llm_api_key="test-key",
        llm_base_url="https://example.test/v1/",
        graph_llm_model="qwen-plus",
        graph_llm_timeout_seconds=30.0,
    )
    base.update(overrides)
    return Settings(**base)  # pyright: ignore[reportArgumentType]


_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}


def _fake_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _patch_completion(monkeypatch, content='{"triples": []}'):
    """把 litellm 调用换成替身，返回记录收到的参数的字典。"""
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response(content)

    monkeypatch.setattr(llm_client, "litellm_completion", fake_completion)
    return captured


def test_chat_json_passes_settings_to_litellm(monkeypatch):
    captured = _patch_completion(monkeypatch)

    result = llm_client.chat_json(_settings(), "只输出 JSON", "卡片正文", _SCHEMA)

    assert result == '{"triples": []}'
    assert captured["model"] == "openai/qwen-plus"
    assert captured["api_key"] == "test-key"
    assert captured["api_base"] == "https://example.test/v1"  # 末尾斜杠已去掉
    assert captured["timeout"] == 30.0
    assert captured["num_retries"] == 0
    assert captured["temperature"] == 0
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"] == [
        {"role": "system", "content": "只输出 JSON"},
        {"role": "user", "content": "卡片正文"},
    ]


def test_model_with_provider_prefix_is_kept(monkeypatch):
    captured = _patch_completion(monkeypatch)

    llm_client.chat_json(_settings(graph_llm_model="dashscope/qwen-plus"), "s", "u", _SCHEMA)

    assert captured["model"] == "dashscope/qwen-plus"


@pytest.mark.parametrize(
    "field, env_name",
    [
        ("llm_api_key", "LLM_API_KEY"),
        ("llm_base_url", "LLM_BASE_URL"),
        ("graph_llm_model", "GRAPH_LLM_MODEL"),
    ],
)
def test_missing_config_raises_before_calling_model(monkeypatch, field, env_name):
    def must_not_call(**_):
        raise AssertionError("配置缺失时不应调用模型")

    monkeypatch.setattr(llm_client, "litellm_completion", must_not_call)

    with pytest.raises(llm_client.LLMConfigError, match=env_name):
        llm_client.chat_json(_settings(**{field: ""}), "s", "u", _SCHEMA)


@pytest.mark.parametrize("content", [None, "", "   ", "\n\t "])
def test_empty_or_blank_content_raises(monkeypatch, content):
    _patch_completion(monkeypatch, content)

    with pytest.raises(llm_client.LLMResponseError, match="空内容"):
        llm_client.chat_json(_settings(), "s", "u", _SCHEMA)


def test_provider_errors_are_not_swallowed(monkeypatch):
    def boom(**_):
        raise TimeoutError("upstream timeout")

    monkeypatch.setattr(llm_client, "litellm_completion", boom)

    with pytest.raises(TimeoutError):
        llm_client.chat_json(_settings(), "s", "u", _SCHEMA)


def test_with_schema_uses_json_schema_strict(monkeypatch):
    captured = _patch_completion(monkeypatch)
    schema = _SCHEMA

    llm_client.chat_json(_settings(), "s", "u", schema=schema)

    assert captured["response_format"] == {
        "type": "json_schema",
        # strict 在 json_schema 对象内部，与 name、schema 同层
        "json_schema": {"name": "extraction_result", "strict": True, "schema": schema},
    }


def test_schema_does_not_skip_config_check(monkeypatch):
    def must_not_call(**_):
        raise AssertionError("配置缺失时不应调用模型")

    monkeypatch.setattr(llm_client, "litellm_completion", must_not_call)
    with pytest.raises(llm_client.LLMConfigError, match="GRAPH_LLM_MODEL"):
        llm_client.chat_json(_settings(graph_llm_model=""), "s", "u", schema={"type": "object"})

