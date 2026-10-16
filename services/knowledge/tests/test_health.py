"""知识库服务健康检查。"""

from fastapi.testclient import TestClient

from knowledge_service.app import create_app


def test_health():
    with TestClient(create_app()) as client:
        r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "embedding_model" in data
    assert "rerank_model" in data
    assert "indexed_chunks" in data
