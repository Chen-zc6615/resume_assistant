"""上传安全校验测试：加密（S09）/伪造/超限/路径穿越。

解析能力已迁移到独立解析服务，本文件只保留主服务侧的上传预检
（委托 resume_shared.pdf_validation）。损坏文件（S10）上传预检会放行
（pymupdf 容忍截断），由解析服务在解析阶段拒绝（见 parser 服务测试）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app_service.core.security import (
    FileValidationError,
    ensure_safe_file_key,
    validate_upload,
)

from tests.conftest import golden


def test_s09_encrypted_rejected():
    """S09 加密 PDF：上传校验链友好拒绝。"""
    content = Path(golden("sample09_加密PDF_异常上传.pdf")).read_bytes()
    with pytest.raises(FileValidationError, match="加密"):
        validate_upload(content)


def test_fake_pdf_magic_rejected():
    """伪 PDF（文本文件改名）：魔数嗅探拦截。"""
    with pytest.raises(FileValidationError, match="不是有效的 PDF"):
        validate_upload(b"plain text pretending to be pdf")


def test_oversize_rejected():
    from app_service.core.config import get_settings

    limit = get_settings().max_upload_size_mb * 1024 * 1024
    with pytest.raises(FileValidationError, match="大于"):
        validate_upload(b"%PDF-1.4" + b"x" * (limit + 1))


def test_safe_file_key_guard():
    """存储键必须是 64 位十六进制 + .pdf，防路径穿越。"""
    with pytest.raises(FileValidationError):
        ensure_safe_file_key("../etc/passwd")
    assert ensure_safe_file_key("a" * 64 + ".pdf") == "a" * 64 + ".pdf"
