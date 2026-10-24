from openai import OpenAI

from app_service.core.config import get_settings
from app_service.core.logger import get_logger

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
