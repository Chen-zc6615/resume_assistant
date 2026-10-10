"""大模型客户端封装：DashScope OpenAI 兼容模式（qwen-plus 提取 / qwen-vl-max OCR）。"""

from __future__ import annotations

import base64

from openai import OpenAI

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)


def get_client() -> OpenAI:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY（.env）")
    return OpenAI(api_key=settings.dashscope_api_key, base_url=settings.llm_base_url)


def chat_json(system_prompt: str, user_content: str) -> str:
    """结构化提取：强约束 JSON 输出。超时/异常由调用方重试。"""
    settings = get_settings()
    client = get_client()
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        timeout=settings.llm_timeout_seconds,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("模型返回空内容")
    return content


def ocr_pdf_page_png(png_bytes: bytes) -> str:
    """qwen-vl-max 视觉理解：从简历页面图片中抽出文字。"""
    settings = get_settings()
    client = get_client()
    b64 = base64.b64encode(png_bytes).decode()
    resp = client.chat.completions.create(
        model=settings.ocr_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {
                        "type": "text",
                        "text": "请识别这张简历图片中的全部文字，按从上到下、从左到右的阅读顺序输出纯文本，不要输出任何解释。",
                    },
                ],
            }
        ],
        temperature=0.1,
        timeout=settings.parse_timeout_seconds * 3,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("OCR 返回空内容")
    return content
