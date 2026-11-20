"""解析服务 PDF 复检单测（合成输入，不依赖黄金样本）。"""

from __future__ import annotations

import pytest

from parser_service.core.config import Settings
from parser_service.services.security import FileValidationError, validate_pdf

SETTINGS = Settings(max_upload_size_mb=1)
MAX = 1024 * 1024


def test_empty_rejected():
    with pytest.raises(FileValidationError, match="文件为空"):
        validate_pdf(b"", SETTINGS)


def test_oversize_rejected():
    with pytest.raises(FileValidationError, match="大于"):
        validate_pdf(b"%PDF-" + b"x" * MAX, SETTINGS)


def test_fake_magic_rejected():
    with pytest.raises(FileValidationError, match="不是有效的 PDF"):
        validate_pdf(b"not a pdf", SETTINGS)


def test_corrupt_rejected():
    with pytest.raises(FileValidationError, match="已损坏"):
        validate_pdf(b"%PDF-1.4 garbage", SETTINGS)
