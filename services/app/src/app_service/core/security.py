"""文件安全：PDF 校验委托 resume_shared，大小上限取自本服务配置。

保持既有函数名与异常类型不变，供 upload_service 与测试继续使用。
"""

from __future__ import annotations

from resume_shared.pdf_validation import (
    PDF_MAGIC,
    FileValidationError,
    ensure_safe_file_key,
    validate_openable,
    validate_pdf_magic,
)
from resume_shared.pdf_validation import validate_size as _validate_size

from app_service.core.config import get_settings

__all__ = [
    "PDF_MAGIC",
    "FileValidationError",
    "ensure_safe_file_key",
    "validate_openable",
    "validate_pdf_magic",
    "validate_size",
    "validate_upload",
]


def validate_size(content: bytes) -> None:
    """大小校验（上限取本服务 max_upload_size_mb 配置）。"""
    _validate_size(content, get_settings().max_upload_size_mb * 1024 * 1024)


def validate_upload(content: bytes) -> None:
    """上传校验链：大小 -> 魔数 -> 可打开。"""
    validate_size(content)
    validate_pdf_magic(content)
    validate_openable(content)
