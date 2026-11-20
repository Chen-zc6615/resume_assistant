"""文件安全：解析前复检（大小、魔数、加密/损坏检测）。

主服务 app_service.core.security 有一份同语义的上传预检实现，
消息文案与异常语义需与之保持一致，改动时两边同步。
"""

from __future__ import annotations

import pymupdf

from parser_service.core.config import Settings

__all__ = ["FileValidationError", "validate_pdf"]

PDF_MAGIC = b"%PDF-"


class FileValidationError(ValueError):
    """上传文件不合规（格式/大小/加密/损坏）。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _validate_size(content: bytes, max_bytes: int) -> None:
    """空文件 / 超出大小上限。"""
    if len(content) == 0:
        raise FileValidationError("文件为空，请重新上传")
    if len(content) > max_bytes:
        raise FileValidationError(
            f"单个文件不能大于 {max_bytes // (1024 * 1024)}M，请重新上传"
        )


def _validate_pdf_magic(content: bytes) -> None:
    """文件类型嗅探：仅凭扩展名不可信（如 S10 伪造文件用例）。"""
    if not content.startswith(PDF_MAGIC):
        raise FileValidationError("文件不是有效的 PDF，请重新上传")


def _validate_openable(content: bytes) -> int:
    """试开校验：检测加密（如 S09）与损坏（如 S10）文件，返回页数。"""
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise FileValidationError("文件已加密或受保护，请重新上传")
            # 触发实际解析以暴露损坏文件
            return doc.page_count
    except FileValidationError:
        raise
    except Exception as exc:
        raise FileValidationError("文件已损坏，解析失败，请重新上传") from exc


def validate_pdf(content: bytes, settings: Settings) -> int:
    """校验上传的 PDF 字节，返回页数；不合规则抛 FileValidationError。

    完整校验链：大小 -> 魔数 -> 可打开。
    """
    _validate_size(content, settings.max_upload_size_mb * 1024 * 1024)
    _validate_pdf_magic(content)
    return _validate_openable(content)
