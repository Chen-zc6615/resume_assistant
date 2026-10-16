from __future__ import annotations

import pymupdf

from parser_service.core.config import Settings

PDF_MAGIC = b"%PDF-"


class FileValidationError(ValueError):
    pass


def validate_pdf(content: bytes, settings: Settings) -> int:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if not content:
        raise FileValidationError("文件为空，请重新上传")
    if len(content) > max_bytes:
        raise FileValidationError(
            f"单个文件不能大于 {settings.max_upload_size_mb}M，请重新上传"
        )
    if not content.startswith(PDF_MAGIC):
        raise FileValidationError("文件不是有效的 PDF，请重新上传")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise FileValidationError("文件已加密或受保护，请重新上传")
            return document.page_count
    except FileValidationError:
        raise
    except Exception as exc:
        raise FileValidationError("文件已损坏，解析失败，请重新上传") from exc

