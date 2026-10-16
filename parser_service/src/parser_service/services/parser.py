from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pdfplumber
import pymupdf

from parser_service.core.config import Settings
from parser_service.services.ocr import OCRClient
from parser_service.services.security import validate_pdf


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseResult:
    text: str
    parse_method: str
    page_count: int
    used_ocr: bool
    effective_chars: int
    warnings: list[str]


def count_effective_chars(text: str | None) -> int:
    if not text:
        return 0
    return sum(1 for character in text if character.isprintable() and not character.isspace())


def extract_with_pymupdf(content: bytes) -> str:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return "\n".join(page.get_text("text") for page in document)


def extract_with_pdfplumber(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def render_page_pngs(content: bytes) -> list[bytes]:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return [page.get_pixmap(dpi=150).tobytes("png") for page in document]


def parse_pdf(content: bytes, settings: Settings) -> ParseResult:
    page_count = validate_pdf(content, settings)
    warnings: list[str] = []

    try:
        text = extract_with_pymupdf(content)
        chars = count_effective_chars(text)
        if chars >= settings.min_effective_chars:
            return ParseResult(text, "pymupdf", page_count, False, chars, warnings)
        warnings.append(f"PyMuPDF 有效字符不足：{chars}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"PyMuPDF 解析失败：{exc}")

    try:
        text = extract_with_pdfplumber(content)
        chars = count_effective_chars(text)
        if chars >= settings.min_effective_chars:
            return ParseResult(text, "pdfplumber", page_count, False, chars, warnings)
        warnings.append(f"pdfplumber 有效字符不足：{chars}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pdfplumber 解析失败：{exc}")

    pages = render_page_pngs(content)
    if not pages:
        raise RuntimeError("PDF 没有有效页面")

    last_error: Exception | None = None
    for attempt in range(1, settings.ocr_max_retries + 1):
        try:
            ocr = OCRClient(settings)
            text = "\n".join(ocr.recognize_png(page) for page in pages)
            chars = count_effective_chars(text)
            if chars >= settings.min_effective_chars:
                return ParseResult(text, settings.ocr_model, page_count, True, chars, warnings)
            last_error = RuntimeError(f"OCR 结果有效字符不足：{chars}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("OCR 第 %s 次失败：%s", attempt, exc)
    raise last_error or RuntimeError("OCR 解析失败")

