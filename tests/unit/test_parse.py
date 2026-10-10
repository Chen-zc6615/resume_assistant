"""解析逻辑测试：文本提取、有效字符、异常文件（黄金样本 S01/S05/S09/S10）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.security import FileValidationError, validate_upload
from src.services.parse_service import effective_chars, extract_with_pymupdf, parse_pdf
from tests.conftest import golden


def test_effective_chars():
    assert effective_chars(None) == 0
    assert effective_chars("") == 0
    assert effective_chars("  \n\t abc \n") == 3
    assert effective_chars("张三\n男\n13800001111") == len("张三男13800001111")


def test_s01_text_pdf_extractable():
    """S01 文本型简历：PyMuPDF 直接提取出足量文本。"""
    text = extract_with_pymupdf(Path(golden("sample01_完美匹配_高分正样本.pdf")))
    assert effective_chars(text) >= 50
    assert "Java" in text or "java" in text.lower()


def test_s05_scanned_pdf_no_text_layer():
    """S05 扫描件：直接文本提取应为空（走 OCR 链路的触发条件）。"""
    text = extract_with_pymupdf(Path(golden("sample05_扫描件_图片型简历.pdf")))
    assert effective_chars(text) < 50


def test_s09_encrypted_rejected():
    """S09 加密 PDF：上传校验链友好拒绝。"""
    content = Path(golden("sample09_加密PDF_异常上传.pdf")).read_bytes()
    with pytest.raises(FileValidationError, match="加密"):
        validate_upload(content)


def test_s10_corrupted_rejected():
    """S10 损坏 PDF：上传或解析阶段必须失败，不得静默。"""
    content = Path(golden("sample10_损坏PDF_异常上传.pdf")).read_bytes()
    try:
        validate_upload(content)
    except FileValidationError:
        return  # 上传阶段拦截，符合预期
    # 若上传阶段放行（pymupdf 容忍截断），解析阶段必须报错
    with pytest.raises(Exception):
        parse_pdf(Path(golden("sample10_损坏PDF_异常上传.pdf")))


def test_fake_pdf_magic_rejected():
    """伪 PDF（文本文件改名）：魔数嗅探拦截。"""
    with pytest.raises(FileValidationError, match="不是有效的 PDF"):
        validate_upload(b"plain text pretending to be pdf")


def test_oversize_rejected():
    from src.core.config import get_settings

    limit = get_settings().max_upload_size_mb * 1024 * 1024
    with pytest.raises(FileValidationError, match="大于"):
        validate_upload(b"%PDF-1.4" + b"x" * (limit + 1))
