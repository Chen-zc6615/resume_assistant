"""解析服务契约测试：/api/v1/parse 的输入输出与异常（黄金样本 S01/S09/S10）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from parser_service.app import create_app
from tests.conftest import golden


@pytest.fixture()
def client():
    # raise_server_exceptions=False：让未捕获异常返回 500 响应而非直接抛出，
    # 便于断言「损坏文件必须失败」的服务端行为。
    return TestClient(create_app(), raise_server_exceptions=False)


def _parse(client: TestClient, filename: str):
    content = Path(golden(filename)).read_bytes()
    return client.post("/api/v1/parse", files={"file": (filename, content, "application/pdf")})


def test_s01_text_pdf_parsed(client):
    """S01 文本型简历：直接提取出足量文本，不走 OCR。"""
    r = _parse(client, "sample01_完美匹配_高分正样本.pdf")
    assert r.status_code == 200
    data = r.json()
    assert data["effective_chars"] >= 50
    assert data["parse_method"] in ("pymupdf", "pdfplumber")
    assert data["used_ocr"] is False
    assert data["text"]
    assert isinstance(data["warnings"], list)


def test_s05_scanned_pdf_needs_ocr(client, monkeypatch):
    """S05 扫描件：直接文本不足，走 OCR 兜底（打桩 OCR 客户端）。"""
    from parser_service.clients import vision_client

    monkeypatch.setattr(
        vision_client.VisionClient,
        "recognize_png",
        lambda self, png: "张三 后端工程师 Java MySQL " * 10,  # 足量文本
    )
    r = _parse(client, "sample05_扫描件_图片型简历.pdf")
    assert r.status_code == 200
    assert r.json()["used_ocr"] is True


def test_s09_encrypted_422(client):
    """S09 加密 PDF：校验拒绝，返回 422。"""
    r = _parse(client, "sample09_加密PDF_异常上传.pdf")
    assert r.status_code == 422
    assert "加密" in r.json()["detail"]


def test_fake_pdf_422(client):
    """伪 PDF：魔数校验拒绝，返回 422。"""
    r = client.post(
        "/api/v1/parse",
        files={"file": ("fake.pdf", b"plain text pretending to be pdf", "application/pdf")},
    )
    assert r.status_code == 422
    assert "不是有效的 PDF" in r.json()["detail"]


def test_s10_corrupted_fails(client):
    """S10 损坏 PDF：必须失败（422 校验拒绝或 500 解析异常），不得静默成功。"""
    r = _parse(client, "sample10_损坏PDF_异常上传.pdf")
    assert r.status_code in (422, 500)
