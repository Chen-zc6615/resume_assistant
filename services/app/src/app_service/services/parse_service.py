"""解析服务：PyMuPDF -> pdfplumber -> OCR(qwen-vl-max) 三级兜底（F-01 后半段）。

降级契约（PRD/SPEC）：
- 文本有效字符数 >= 50 视为解析成功；
- 文本提取为空的扫描件自动触发 OCR；
- 各级失败均重试 2 次，仍失败 -> 解析失败列表，提示人工审核。
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pymupdf

from app_service.core.config import get_settings
from app_service.core.logger import get_logger
from app_service.services import llm

logger = get_logger(__name__)

PARSE_MAX_RETRIES = 2  # SPEC：解析超时/失败重试 2 次


def effective_chars(text: str | None) -> int:
    """有效字符数（去除空白与控制字符）。"""
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace() and ch.isprintable())


def extract_with_pymupdf(pdf_path: Path) -> str:
    doc = pymupdf.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def extract_with_pdfplumber(pdf_path: Path) -> str:
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _render_page_pngs(pdf_path: Path) -> list[bytes]:
    doc = pymupdf.open(pdf_path)
    try:
        return [page.get_pixmap(dpi=150).tobytes("png") for page in doc]
    finally:
        doc.close()


def extract_with_ocr(pdf_path: Path) -> str:
    """整份简历逐页 OCR，任一页失败即整体失败（由上层重试）。"""
    pages = _render_page_pngs(pdf_path)
    if not pages:
        raise ValueError("PDF 无有效页面")
    texts = [llm.ocr_pdf_page_png(png) for png in pages]
    return "\n".join(texts)


def parse_pdf(pdf_path: Path) -> str:
    """三级解析链，返回原始文本；全部失败抛出最后一次异常。"""
    settings = get_settings()

    # 第一级：PyMuPDF（速度快）
    text = extract_with_pymupdf(pdf_path)
    if effective_chars(text) >= settings.min_effective_chars:
        return text

    # 第二级：pdfplumber（表格/布局更好）
    try:
        text = extract_with_pdfplumber(pdf_path)
        if effective_chars(text) >= settings.min_effective_chars:
            return text
    except Exception as e:  # noqa: BLE001
        logger.warning("pdfplumber 解析失败 %s: %s", pdf_path.name, e)

    # 第三级：OCR 兜底（扫描件/图片型），重试 2 次
    last_error: Exception | None = None
    for attempt in range(1, PARSE_MAX_RETRIES + 1):
        try:
            text = extract_with_ocr(pdf_path)
            if effective_chars(text) >= settings.min_effective_chars:
                return text
            last_error = ValueError(f"OCR 结果有效字符不足（{effective_chars(text)}）")
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning("OCR 第 %s 次失败 %s: %s", attempt, pdf_path.name, e)
    raise last_error or ValueError("OCR 解析失败")
