"""chat_stream 的流式聚合单测：content 增量与 tool_calls 分片拼接。"""

from __future__ import annotations

from typing import Any

import pytest
from app_service.db.base import Base
from app_service.db.session import SessionLocal, engine
from app_service.services import agent_service


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ---- OpenAI 流式协议的最小仿真对象 ----


class _Function:
    def __init__(self, name: str | None = None, arguments: str | None = None):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, index: int, id: str | None = None, name: str | None = None,
                 arguments: str | None = None):
        self.index = index
        self.id = id
        self.function = _Function(name, arguments)


class _Delta:
    def __init__(self, content: str | None = None, tool_calls: list[_ToolCall] | None = None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta: _Delta):
        self.delta = delta


class _Chunk:
    def __init__(self, delta: _Delta):
        self.choices = [_Choice(delta)]


class _IntentMessage:
    def __init__(self, content: str):
        self.content = content


class _IntentChoice:
    def __init__(self, content: str):
        self.message = _IntentMessage(content)


class _IntentResponse:
    def __init__(self, content: str):
        self.choices = [_IntentChoice(content)]


class _Completions:
    def __init__(self, rounds: list[list[_Chunk]], intent: str):
        self._rounds = rounds
        self._intent = intent
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs.get("stream"):
            return _IntentResponse(self._intent)
        chunks = self._rounds.pop(0)
        assert kwargs.get("stream") is True, "流式端点必须以 stream=True 调用"
        return iter(chunks)


class _Client:
    def __init__(self, rounds: list[list[_Chunk]], intent: str = "DASHBOARD_QUERY"):
        self.chat = type("Chat", (), {})()
        self.chat.completions = _Completions(rounds, intent)


def _run(db, client: _Client) -> list[dict[str, Any]]:
    return list(agent_service.chat_stream(db, "看板", client=client))


def test_stream_aggregates_content_deltas(db):
    """纯文本终答：delta 增量按序产出，final 携带完整 answer 与 traces。"""
    client = _Client([
        # 第一轮：Text2SQL 工具参数故意拆成两片
        [
            _Chunk(_Delta(tool_calls=[_ToolCall(0, id="call-1", name="query_recruitment_database", arguments='{"sql":"SELECT COUNT(resume_id) AS total FROM resumes",')])),
            _Chunk(_Delta(tool_calls=[_ToolCall(0, arguments='"purpose":"统计简历数量"}')])),
        ],
        # 第二轮：终答文本分三片
        [
            _Chunk(_Delta(content="您好，")),
            _Chunk(_Delta(content="当前系统共有 ")),
            _Chunk(_Delta(content="0 份简历。")),
        ],
    ])

    events = _run(db, client)

    intents = [e for e in events if e["type"] == "intent"]
    deltas = [e for e in events if e["type"] == "delta"]
    tools = [e for e in events if e["type"] == "tool"]
    finals = [e for e in events if e["type"] == "final"]

    assert intents == [{"type": "intent", "intent": "DASHBOARD_QUERY"}]
    assert [d["text"] for d in deltas][:3] == ["您好，", "当前系统共有 ", "0 份简历。"]
    assert len(tools) == 1
    assert tools[0]["name"] == "query_recruitment_database"
    assert tools[0]["success"] is True
    assert len(finals) == 1
    assert finals[0]["response"].answer.startswith("您好，当前系统共有 0 份简历。")
    assert "[来源: DB:resumes]" in finals[0]["response"].answer
    # 工具轨迹进入 final response（与同步版契约一致），分片拼接出完整参数
    trace = finals[0]["response"].tool_traces[0]
    assert trace.tool == "query_recruitment_database"
    assert trace.success is True
    assert trace.arguments["purpose"] == "统计简历数量"


def test_stream_rejects_invalid_tool_json(db):
    """分片拼接出非法 JSON 时，工具失败事件与 trace 与同步版同构。"""
    client = _Client([
        [
            _Chunk(_Delta(tool_calls=[_ToolCall(0, id="call-x", name="query_recruitment_database", arguments='{"broken"')])),
        ],
        [_Chunk(_Delta(tool_calls=[_ToolCall(0, id="call-ok", name="query_recruitment_database", arguments='{"sql":"SELECT COUNT(resume_id) AS total FROM resumes","purpose":"恢复查询"}')] ))],
        [
            _Chunk(_Delta(content="已收到错误反馈。")),
        ],
    ])

    events = _run(db, client)

    tools = [e for e in events if e["type"] == "tool"]
    finals = [e for e in events if e["type"] == "final"]
    assert tools[0]["success"] is False
    assert finals[0]["response"].tool_traces[0].success is False
    assert finals[0]["response"].answer.startswith("已收到错误反馈。")


def test_stream_empty_answer_raises_protocol_error(db):
    """终轮无内容且无工具调用：与同步版一致抛 AgentProtocolError。"""
    client = _Client([
        [_Chunk(_Delta(content=None))],
    ])
    with pytest.raises(agent_service.AgentProtocolError):
        _run(db, client)


def test_stream_unsupported_short_circuits_without_agent_tool_loop(db):
    client = _Client([], intent="UNSUPPORTED")

    events = _run(db, client)

    assert [event["type"] for event in events] == ["intent", "delta", "final"]
    assert events[0]["intent"] == "UNSUPPORTED"
    assert "不属于当前招聘" in events[1]["text"]
    assert len(client.chat.completions.calls) == 1


def test_stream_limits_tools_to_classified_intent(db):
    client = _Client(
        [[_Chunk(_Delta(tool_calls=[_ToolCall(0, id="call-1", name="query_recruitment_database", arguments='{"sql":"SELECT COUNT(resume_id) AS total FROM resumes","purpose":"看板"}')]))],
         [_Chunk(_Delta(content="看板查询完成。"))]], intent="DASHBOARD_QUERY"
    )

    _run(db, client)

    agent_call = client.chat.completions.calls[1]
    assert [tool["function"]["name"] for tool in agent_call["tools"]] == [
        "query_recruitment_database"
    ]


def test_invalid_router_label_uses_closed_world_fallback(db):
    client = _Client([], intent="SOMETHING_ELSE")

    events = _run(db, client)

    assert events[0] == {"type": "intent", "intent": "UNSUPPORTED"}
    assert len(client.chat.completions.calls) == 1


def test_sync_chat_unsupported_short_circuits_without_agent_tool_loop(db):
    client = _Client([], intent="UNSUPPORTED")

    response = agent_service.chat(db, "替我直接删除这份简历", client=client)

    assert "不会直接修改、删除" in response.answer
    assert response.tool_traces == []
    assert len(client.chat.completions.calls) == 1
