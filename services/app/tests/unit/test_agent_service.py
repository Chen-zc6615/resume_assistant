from types import SimpleNamespace
from unittest.mock import Mock

from app_service.services import agent_service


def test_chat_uses_injected_litellm_completion():
    captured = {}
    assistant = SimpleNamespace(
        content="当前共有 3 份待审核简历。",
        tool_calls=[],
        model_dump=lambda **_: {
            "role": "assistant",
            "content": "当前共有 3 份待审核简历。",
        },
    )

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=assistant)])

    result = agent_service.chat(
        Mock(),
        "现在有多少待审核简历？",
        completion_fn=fake_completion,
    )

    assert result.answer == "当前共有 3 份待审核简历。"
    assert result.tool_traces == []
    assert captured["messages"][1] == {
        "role": "user",
        "content": "现在有多少待审核简历？",
    }
    assert captured["tools"] == agent_service.AGENT_TOOLS


def test_search_talent_knowledge_tool_uses_knowledge_client(monkeypatch):
    response = SimpleNamespace(
        query="Python 项目",
        latency_ms=8.2,
        results=[
            SimpleNamespace(
                chunk_id="talent-1:abc",
                document_id="talent-1",
                content="负责 Python API 项目",
                metadata={"source_resume_id": 1},
                rerank_score=0.93,
            )
        ],
    )
    monkeypatch.setattr(agent_service.knowledge_client, "search", lambda query: response)

    success, result = agent_service.execute_tool(
        Mock(), "search_talent_knowledge", {"query": "Python 项目"}
    )

    assert success is True
    assert result["query"] == "Python 项目"
    assert result["results"][0]["document_id"] == "talent-1"
