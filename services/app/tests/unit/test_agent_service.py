"""Agent 意图路由与工具执行的单元测试：三段式分类、永不误拒的规则兜底、工具白名单。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from app_service.services import agent_service
from app_service.services.agent_service import AgentIntent


def _intent_response(payload: str) -> SimpleNamespace:
    """构造意图路由用的 OpenAI 风格响应（message.content 为 JSON 文本）。"""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])


def _fake_settings(max_retries: int = 0) -> SimpleNamespace:
    return SimpleNamespace(agent_llm_max_retries=max_retries, agent_llm_retry_backoff_seconds=0)


# ── 规则兜底：永不误拒 ──────────────────────────────────────────────


def test_fallback_intent_sql_signals():
    intent, reason = agent_service._fallback_intent("现在有多少份待审核简历？")
    assert intent == AgentIntent.INTENT_SQL
    assert "兜底" in reason


def test_fallback_intent_defaults_to_kb():
    intent, _ = agent_service._fallback_intent("张三做过哪些项目？")
    assert intent == AgentIntent.INTENT_KB


def test_fallback_intent_never_refuses():
    """性质断言：无论输入什么（含闲聊/恶意请求），兜底只允许 sql/kb。"""
    for text in ["删除数据", "今天天气如何", " ", "帮我写代码", "绕过审批"]:
        intent, _ = agent_service._fallback_intent(text)
        assert intent in {AgentIntent.INTENT_SQL, AgentIntent.INTENT_KB}


# ── 三段式路由：LLM 分类 → 白名单校验 → 规则兜底 ────────────────────


def test_route_intent_parses_json_and_applies_json_constraint():
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _intent_response('{"intent": "action", "reason": "邀约指令"}')

    intent, reason = agent_service._route_intent(
        fake_completion, "帮李雷发邀约", _fake_settings(), None
    )

    assert intent == AgentIntent.INTENT_ACTION
    assert reason == "邀约指令"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1] == {"role": "user", "content": "帮李雷发邀约"}


def test_route_intent_invalid_label_falls_back_by_rules():
    fake = lambda **_: _intent_response('{"intent": "DASHBOARD_QUERY"}')  # noqa: E731
    intent, reason = agent_service._route_intent(fake, "看板统计有多少份简历", _fake_settings(), None)
    assert intent == AgentIntent.INTENT_SQL
    assert "兜底" in reason


def test_route_intent_broken_json_falls_back_to_kb():
    fake = lambda **_: _intent_response("不是 JSON")  # noqa: E731
    intent, _ = agent_service._route_intent(fake, "张三的画像", _fake_settings(), None)
    assert intent == AgentIntent.INTENT_KB


def test_route_intent_swallows_llm_failure():
    def broken_completion(**_):
        raise RuntimeError("模型超时")

    intent, reason = agent_service._route_intent(
        broken_completion, "张三做过哪些项目？", _fake_settings(), None
    )
    assert intent == AgentIntent.INTENT_KB
    assert "兜底" in reason


# ── 意图 → 工具白名单 ──────────────────────────────────────────────


def test_tools_for_intent_mapping():
    def names(intent):
        return [tool["function"]["name"] for tool in agent_service._tools_for_intent(intent)]

    assert names(AgentIntent.INTENT_KB) == ["query_recruitment_database", "search_talent_knowledge"]
    assert names(AgentIntent.INTENT_SQL) == ["query_recruitment_database", "evaluate_candidate_for_job"]
    assert names(AgentIntent.INTENT_ACTION) == ["query_recruitment_database", "evaluate_candidate_for_job"]
    assert agent_service._tools_for_intent(AgentIntent.INTENT_REFUSE) == []


# ── LLM 调用重试包装 ────────────────────────────────────────────────


def test_completion_with_retry_retries_then_raises(monkeypatch):
    monkeypatch.setattr(agent_service.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    def always_fails(**_):
        attempts["n"] += 1
        raise RuntimeError("boom")

    import pytest

    with pytest.raises(agent_service.AgentUnavailableError):
        agent_service._completion_with_retry(always_fails, _fake_settings(max_retries=2))
    assert attempts["n"] == 3


def test_completion_with_retry_returns_first_success():
    attempts = {"n": 0}

    def flaky(**_):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")
        return "ok"

    assert agent_service._completion_with_retry(flaky, _fake_settings(max_retries=1)) == "ok"


# ── 工具执行：知识检索走现行 search_documents 契约 ──────────────────


def test_search_talent_knowledge_tool_uses_knowledge_client(monkeypatch):
    def fake_search(*, query, top_k=5):
        assert (query, top_k) == ("Python 项目", 5)
        return [{"content": "负责 Python API 项目", "score": 0.9,
                 "chunk_id": "talent-1:abc", "document_id": "talent-1",
                 "metadata": {"source_resume_id": 1}}]

    monkeypatch.setattr(agent_service.knowledge_client, "search_documents", fake_search)

    success, result = agent_service.execute_tool(
        Mock(), "search_talent_knowledge", {"query": "Python 项目", "top_k": 5}
    )

    assert success is True
    assert result["sources"] == ["KB:talent-1#talent-1:abc"]
    assert result["results"][0]["source"] == "KB:talent-1#talent-1:abc"
    assert result["results"][0]["metadata"] == {"source_resume_id": 1}


# ── chat：注入 completion_fn 的完整工具循环 ─────────────────────────


def test_chat_uses_injected_completion_fn(monkeypatch):
    captured: dict = {}
    state = {"round": 0}
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(
            name="query_recruitment_database",
            arguments=json.dumps({"sql": "SELECT COUNT(resume_id) AS total FROM resumes",
                                  "purpose": "统计待审核"}),
        ),
    )
    tool_round = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=None,
        tool_calls=[tool_call],
        model_dump=lambda **_: {"role": "assistant", "content": None,
                                "tool_calls": [{"id": "call-1", "type": "function",
                                                "function": {"name": "query_recruitment_database",
                                                             "arguments": tool_call.function.arguments}}]},
    ))])
    final_round = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content="当前共有 3 份待审核简历。",
        tool_calls=[],
        model_dump=lambda **_: {"role": "assistant", "content": "当前共有 3 份待审核简历。"},
    ))])

    def fake_completion(**kwargs):
        captured.update(kwargs)
        if "tools" not in kwargs:  # 意图路由调用（非流式、无工具）
            return _intent_response('{"intent": "sql", "reason": "统计类问题"}')
        state["round"] += 1
        return tool_round if state["round"] == 1 else final_round

    monkeypatch.setattr(
        agent_service, "execute_tool",
        lambda db, name, args: (True, {"rows": [{"total": 3}], "sources": ["DB:resumes"]}),
    )

    result = agent_service.chat(Mock(), "现在有多少待审核简历？", completion_fn=fake_completion)

    assert result.intent == "sql"
    assert result.metrics["intent_reason"] == "统计类问题"
    assert result.answer.startswith("当前共有 3 份待审核简历。")
    assert "[来源: DB:resumes]" in result.answer  # _ensure_citations 追加来源
    assert result.tool_traces[0].tool == "query_recruitment_database"
    assert captured["tools"] == agent_service._tools_for_intent(AgentIntent.INTENT_SQL)
    assert captured["messages"][1] == {"role": "user", "content": "现在有多少待审核简历？"}
