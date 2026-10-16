"""解析 HTTP 客户端测试：请求形状、状态码映射、重试与不可用语义（打桩 httpx）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app_service.clients import parser_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """替代 httpx.Client：按序返回预置响应；可配置抛连接错误。"""

    def __init__(self, responses, raise_error: Exception | None = None):
        self._responses = list(responses)
        self._raise = raise_error
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, files=None):
        self.calls.append((url, files))
        if self._raise is not None:
            raise self._raise
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """去掉重试退避等待，加速测试。"""
    monkeypatch.setattr(parser_client.time, "sleep", lambda *_: None)


@pytest.fixture()
def pdf_path(tmp_path: Path) -> Path:
    p = tmp_path / "resume.pdf"
    p.write_bytes(b"%PDF-1.4 fake body")
    return p


def _patch_client(monkeypatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(parser_client.httpx, "Client", lambda *a, **k: fake)


def test_success_maps_response(monkeypatch, pdf_path):
    fake = _FakeClient(
        [
            _FakeResponse(
                200,
                {
                    "text": "张三 简历",
                    "parse_method": "pymupdf",
                    "page_count": 2,
                    "used_ocr": False,
                    "effective_chars": 42,
                    "warnings": [],
                },
            )
        ]
    )
    _patch_client(monkeypatch, fake)

    result = parser_client.parse_resume_via_service(pdf_path)

    assert result.text == "张三 简历"
    assert result.parse_method == "pymupdf"
    assert result.page_count == 2
    # 请求形状：URL 指向 /api/v1/parse，multipart 字段名为 file
    url, files = fake.calls[0]
    assert url.endswith("/api/v1/parse")
    assert "file" in files


def test_422_raises_without_retry(monkeypatch, pdf_path):
    fake = _FakeClient([_FakeResponse(422, {"detail": "文件已加密或受保护，请重新上传"})])
    _patch_client(monkeypatch, fake)

    with pytest.raises(parser_client.ParserServiceError, match="加密"):
        parser_client.parse_resume_via_service(pdf_path)

    assert len(fake.calls) == 1  # 文件不合规不重试


def test_5xx_retries_then_unavailable(monkeypatch, pdf_path):
    fake = _FakeClient([_FakeResponse(500, {"detail": "OCR 失败"}), _FakeResponse(500)])
    _patch_client(monkeypatch, fake)

    with pytest.raises(parser_client.ParserServiceError, match="解析服务不可用"):
        parser_client.parse_resume_via_service(pdf_path)

    assert len(fake.calls) == 2  # 首次 + 1 次重试


def test_connection_error_unavailable(monkeypatch, pdf_path):
    import httpx

    fake = _FakeClient([], raise_error=httpx.ConnectError("connection refused"))
    _patch_client(monkeypatch, fake)

    with pytest.raises(parser_client.ParserServiceError, match="解析服务不可用"):
        parser_client.parse_resume_via_service(pdf_path)

    assert len(fake.calls) == 2


def test_recovers_after_transient_failure(monkeypatch, pdf_path):
    """首次连接失败、重试成功，应正常返回。"""
    import httpx

    class _FlakyClient:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, files=None):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("boom")
            return _FakeResponse(200, {"text": "ok", "effective_chars": 5})

    flaky = _FlakyClient()
    monkeypatch.setattr(parser_client.httpx, "Client", lambda *a, **k: flaky)

    result = parser_client.parse_resume_via_service(pdf_path)
    assert result.text == "ok"
    assert flaky.calls == 2
