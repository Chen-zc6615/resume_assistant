"""文件安全：PDF 校验委托 resume_shared。"""

from __future__ import annotations

from resume_shared.pdf_validation import (
    FileValidationError,
    validate_pdf_bytes,
)

from parser_service.core.config import Settings

__all__ = ["FileValidationError", "validate_pdf"]


def validate_pdf(content: bytes, settings: Settings) -> int:
    """校验上传的 PDF 字节，返回页数；不合规则抛 FileValidationError。"""
    return validate_pdf_bytes(content, settings.max_upload_size_mb * 1024 * 1024)
