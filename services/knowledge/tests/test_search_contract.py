"""知识库检索 API 契约。"""

from fastapi.testclient import TestClient

from knowledge_service.app import create_app


def test_search_returns_empty_when_empty():
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/search", json={"query": "Java 工程师"})
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == []
    assert data["query"] == "Java 工程师"


def test_search_strips_query_and_rejects_removed_fields():
    with TestClient(create_app()) as client:
        valid = client.post("/api/v1/search", json={"query": "  Java 工程师  "})
        empty = client.post("/api/v1/search", json={"query": "   "})
        extra = client.post(
            "/api/v1/search",
            json={"query": "Java 工程师", "top_k": 5},
        )

    assert valid.status_code == 200
    assert valid.json()["query"] == "Java 工程师"
    assert empty.status_code == 422
    assert extra.status_code == 422
