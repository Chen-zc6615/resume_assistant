"""知识库 HTTP 客户端测试：请求契约、错误映射和幂等重试。"""

from __future__ import annotations

import httpx
import pytest
from app_service.clients import knowledge_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses=None, raise_error: Exception | None = None):
        self._responses = list(responses or [])
        self._raise_error = raise_error
        self.calls: list[tuple[str, str, dict | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def put(self, url: str, json: dict):
        self.calls.append(("PUT", url, json))
        if self._raise_error is not None:
            raise self._raise_error
        return self._responses.pop(0)

    def delete(self, url: str):
        self.calls.append(("DELETE", url, None))
        if self._raise_error is not None:
            raise self._raise_error
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(knowledge_client.time, "sleep", lambda *_: None)


def _patch_client(monkeypatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(knowledge_client.httpx, "Client", lambda *args, **kwargs: fake)


def test_upsert_document_sends_expected_contract(monkeypatch):
    fake = _FakeClient([_FakeResponse(200, {"talent_card_id": "talent-23", "chunk_count": 4})])
    _patch_client(monkeypatch, fake)

    result = knowledge_client.upsert_document(
        talent_card_id="talent-23",
        document_type="talent_profile",
        content="# 候选人知识卡片：张三",
        metadata={"source_resume_id": 11},
    )

    assert result == knowledge_client.DocumentWriteResult("talent-23", 4)
    method, url, body = fake.calls[0]
    assert method == "PUT"
    assert url.endswith("/api/v1/talent-cards/talent-23")
    assert body == {
        "document_type": "talent_profile",
        "content": "# 候选人知识卡片：张三",
        "metadata": {"source_resume_id": 11},
    }


def test_upsert_retries_server_error_then_succeeds(monkeypatch):
    fake = _FakeClient(
        [
            _FakeResponse(503, {"detail": "embedding unavailable"}),
            _FakeResponse(200, {"talent_card_id": "talent-1", "chunk_count": 2}),
        ]
    )
    _patch_client(monkeypatch, fake)

    result = knowledge_client.upsert_document(
        talent_card_id="talent-1",
        document_type="talent_profile",
        content="# 卡片",
    )

    assert result.chunk_count == 2
    assert len(fake.calls) == 2


def test_upsert_does_not_retry_invalid_document(monkeypatch):
    fake = _FakeClient([_FakeResponse(422, {"detail": "content 不能为空"})])
    _patch_client(monkeypatch, fake)

    with pytest.raises(knowledge_client.KnowledgeServiceError, match="content 不能为空"):
        knowledge_client.upsert_document(
            talent_card_id="talent-1",
            document_type="talent_profile",
            content="# 卡片",
        )

    assert len(fake.calls) == 1


def test_connection_error_retries_then_reports_unavailable(monkeypatch):
    fake = _FakeClient(raise_error=httpx.ConnectError("connection refused"))
    _patch_client(monkeypatch, fake)

    with pytest.raises(knowledge_client.KnowledgeServiceError, match="知识库服务不可用"):
        knowledge_client.upsert_document(
            talent_card_id="talent-1",
            document_type="talent_profile",
            content="# 卡片",
        )

    assert len(fake.calls) == 2


@pytest.mark.parametrize("status_code", [204, 404])
def test_delete_is_idempotent(monkeypatch, status_code):
    fake = _FakeClient([_FakeResponse(status_code)])
    _patch_client(monkeypatch, fake)

    knowledge_client.delete_document("talent-23")

    assert fake.calls == [
        (
            "DELETE",
            "http://127.0.0.1:8001/api/v1/talent-cards/talent-23",
            None,
        )
    ]


def test_rejects_empty_input_before_http(monkeypatch):
    fake = _FakeClient([])
    _patch_client(monkeypatch, fake)

    with pytest.raises(ValueError, match="talent_card_id"):
        knowledge_client.delete_document("  ")
    with pytest.raises(ValueError, match="content"):
        knowledge_client.upsert_document(
            talent_card_id="talent-1",
            document_type="talent_profile",
            content="  ",
        )

    assert fake.calls == []
