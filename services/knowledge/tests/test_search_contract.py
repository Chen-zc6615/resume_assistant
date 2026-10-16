"""知识库检索契约：空库下 chat 必须拒答（低置信度不编造）。

空库时检索器提前短路，不触发任何模型调用，故离线可测。
"""

from fastapi.testclient import TestClient

from knowledge_service.app import create_app


def test_chat_refused_when_empty():
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/chat", json={"query": "有没有做过后端的候选人"})
    assert r.status_code == 200
    data = r.json()
    assert data["is_refused"] is True
    assert data["citations"] == []
    assert "没有找到" in data["answer"]


def test_search_returns_empty_when_empty():
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/search", json={"query": "Java 工程师"})
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []
    assert data["query"] == "Java 工程师"
