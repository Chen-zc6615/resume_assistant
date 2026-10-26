"""认证 API 集成测试：登录签发、会话校验、鉴权拦截、登出撤销。"""

from __future__ import annotations

import pytest
from app_service.app import create_app
from app_service.core.auth_security import hash_password
from app_service.db.session import SessionLocal
from app_service.models.db_models import UserAccount
from fastapi.testclient import TestClient

TEST_USER = {
    "username": "auth_api_tester",
    "display_name": "测试 HR",
    "password": "Correct-Horse-1",
}


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def seed_user(client):
    # 依赖 client：先触发应用启动（init_db 建表），再写入测试用户
    db = SessionLocal()
    try:
        existing = (
            db.query(UserAccount)
            .filter(UserAccount.username == TEST_USER["username"])
            .one_or_none()
        )
        if existing:
            db.delete(existing)
            db.commit()
        db.add(
            UserAccount(
                username=TEST_USER["username"],
                display_name=TEST_USER["display_name"],
                password_hash=hash_password(TEST_USER["password"]),
                status="normal",
            )
        )
        db.commit()
    finally:
        db.close()
    yield


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"username": TEST_USER["username"], "password": TEST_USER["password"]},
    )
    assert resp.status_code == 200
    return resp.json()


def test_login_success_returns_token_and_user(client):
    data = _login(client)
    assert data["session_token"]
    assert data["user"]["username"] == TEST_USER["username"]
    assert data["user"]["display_name"] == TEST_USER["display_name"]


def test_login_wrong_password_rejected(client):
    resp = client.post(
        "/api/auth/login",
        json={"username": TEST_USER["username"], "password": "wrong"},
    )
    assert resp.status_code == 401


def test_me_requires_and_accepts_token(client):
    assert client.get("/api/auth/me").status_code == 401
    token = _login(client)["session_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == TEST_USER["username"]


def test_business_api_blocked_without_token(client):
    """业务端点必须携带有效会话令牌。"""
    assert client.get("/api/resumes/stats").status_code == 401
    token = _login(client)["session_token"]
    resp = client.get(
        "/api/resumes/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


def test_health_is_public(client):
    assert client.get("/api/auth/health").status_code == 200


def test_logout_revokes_session(client):
    token = _login(client)["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/resumes/stats", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/resumes/stats", headers=headers).status_code == 401
