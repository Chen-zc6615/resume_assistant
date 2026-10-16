"""共享包 PDF 校验单测（合成输入，不依赖黄金样本）。

主服务/解析服务两侧的集成用例见各自 services/*/tests。
"""

from __future__ import annotations

import pytest
from resume_shared.pdf_validation import (
    FileValidationError,
    ensure_safe_file_key,
    validate_pdf_magic,
    validate_size,
)

MAX = 5 * 1024 * 1024


def test_empty_rejected():
    with pytest.raises(FileValidationError, match="文件为空"):
        validate_size(b"", MAX)


def test_oversize_rejected():
    with pytest.raises(FileValidationError, match="大于"):
        validate_size(b"%PDF-" + b"x" * MAX, MAX)


def test_size_ok():
    validate_size(b"%PDF-1.4 tiny", MAX)  # 不抛即通过


def test_fake_magic_rejected():
    with pytest.raises(FileValidationError, match="不是有效的 PDF"):
        validate_pdf_magic(b"not a pdf")


def test_safe_file_key_guard():
    with pytest.raises(FileValidationError, match="非法的存储路径"):
        ensure_safe_file_key("../evil.pdf")
    key = "f" * 64 + ".pdf"
    assert ensure_safe_file_key(key) == key
