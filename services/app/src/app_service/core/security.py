"""文件安全：上传预检（魔数嗅探、大小限制、加密/损坏检测、存储键路径穿越防护）。

解析服务 parser_service.services.security 有一份同语义的复检实现，
消息文案与异常语义需与之保持一致，改动时两边同步。
"""

from __future__ import annotations

import re

import pymupdf

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

PDF_MAGIC = b"%PDF-"
# 相对存储路径仅允许 "sha256.pdf" 形态，杜绝路径穿越
_SAFE_FILE_KEY = re.compile(r"^[0-9a-f]{64}\.pdf$")


class FileValidationError(ValueError):
    """上传文件不合规（格式/大小/加密/损坏）。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_size(content: bytes) -> None:
    """空文件 / 超出大小上限（上限取本服务 max_upload_size_mb 配置）。"""
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(content) == 0:
        raise FileValidationError("文件为空，请重新上传")
    if len(content) > max_bytes:
        raise FileValidationError(
            f"单个文件不能大于 {max_bytes // (1024 * 1024)}M，请重新上传"
        )


def validate_pdf_magic(content: bytes) -> None:
    """文件类型嗅探：仅凭扩展名不可信（如 S10 伪造文件用例）。"""
    if not content.startswith(PDF_MAGIC):
        raise FileValidationError("文件不是有效的 PDF，请重新上传")


def validate_openable(content: bytes) -> int:
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


def validate_upload(content: bytes) -> None:
    """上传校验链：大小 -> 魔数 -> 可打开。"""
    validate_size(content)
    validate_pdf_magic(content)
    validate_openable(content)


def ensure_safe_file_key(file_key: str) -> str:
    """存储键必须是 64 位十六进制 + .pdf，防止路径穿越。"""
    if not _SAFE_FILE_KEY.match(file_key):
        raise FileValidationError("非法的存储路径")
    return file_key
