"""解析服务 HTTP 客户端：将本地 PDF 提交给独立解析服务并取回文本。

契约（services/parser）：
    POST {base}/api/v1/parse   multipart 字段 file
    200  -> ParseResponse{text, parse_method, page_count, used_ocr, effective_chars, warnings}
    422  -> 文件校验失败（加密/损坏/伪造/超限），detail 为中文提示
    5xx  -> 解析服务自身异常（如 OCR 全失败）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app_service.core.config import get_settings
from app_service.core.logger import get_logger

logger = get_logger(__name__)


class ParserServiceError(RuntimeError):
    """解析服务不可用或解析失败；上层据此落为「解析失败」状态供 HR 重试。"""


@dataclass(frozen=True)
class ParseResult:
    text: str
    parse_method: str = ""
    page_count: int = 0
    used_ocr: bool = False
    effective_chars: int = 0
    warnings: list[str] = field(default_factory=list)


def _detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except Exception:  # noqa: BLE001
        detail = None
    return str(detail) if detail else f"HTTP {resp.status_code}"


def parse_resume_via_service(pdf_path: Path) -> ParseResult:
    """提交本地 PDF 给解析服务，返回解析结果。

    失败一律抛 ParserServiceError：
    - 文件不合规（422）：消息为解析服务给出的原因，不重试；
    - 服务不可用（连接失败/超时/5xx）：重试后仍失败，消息含「解析服务不可用」。
    """
    settings = get_settings()
    url = f"{settings.parser_service_base_url.rstrip('/')}/api/v1/parse"
    content = pdf_path.read_bytes()
    timeout = httpx.Timeout(
        connect=settings.parser_http_connect_timeout_seconds,
        read=settings.parser_http_read_timeout_seconds,
        write=settings.parser_http_connect_timeout_seconds,
        pool=settings.parser_http_connect_timeout_seconds,
    )

    attempts = settings.parser_http_max_retries + 1
    last_error = "解析服务不可用"

    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    url, files={"file": (pdf_path.name, content, "application/pdf")}
                )
        except httpx.HTTPError as exc:
            last_error = f"解析服务不可用：{exc}"
            logger.warning(
                "解析服务请求失败（%s/%s）%s: %s", attempt, attempts, pdf_path.name, exc
            )
            if attempt < attempts:
                time.sleep(settings.parser_http_retry_backoff_seconds)
            continue

        if resp.status_code == 200:
            data = resp.json()
            return ParseResult(
                text=data.get("text", ""),
                parse_method=data.get("parse_method", ""),
                page_count=int(data.get("page_count") or 0),
                used_ocr=bool(data.get("used_ocr")),
                effective_chars=int(data.get("effective_chars") or 0),
                warnings=list(data.get("warnings") or []),
            )

        if resp.status_code == 422:
            # 文件本身不合规（加密/损坏/伪造/超限），重试无意义
            raise ParserServiceError(_detail(resp))

        # 其余（含 5xx）：解析服务异常，幂等重试
        last_error = f"解析服务不可用：{_detail(resp)}"
        logger.warning(
            "解析服务返回 %s（%s/%s）%s: %s",
            resp.status_code,
            attempt,
            attempts,
            pdf_path.name,
            _detail(resp),
        )
        if attempt < attempts:
            time.sleep(settings.parser_http_retry_backoff_seconds)

    raise ParserServiceError(last_error)
