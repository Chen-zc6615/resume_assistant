"""解析服务健康检查。"""

from fastapi.testclient import TestClient

from parser_service.app import create_app


def test_health():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "ocr_model" in data
