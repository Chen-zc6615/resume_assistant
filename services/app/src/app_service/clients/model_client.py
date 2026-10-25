"""主服务模型客户端：集中封装 LiteLLM 与任务级模型配置。"""

from collections.abc import Callable
from typing import Any

from litellm import completion as litellm_completion

from app_service.core.config import get_settings


def _litellm_model(model: str) -> str:
    return model if "/" in model else f"openai/{model}"


def _completion(*, model: str, timeout: float, **kwargs: Any) -> Any:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY（.env）")
    return litellm_completion(
        model=_litellm_model(model),
        api_key=settings.dashscope_api_key,
        api_base=settings.llm_base_url.rstrip("/"),
        timeout=timeout,
        num_retries=0,
        **kwargs,
    )


def complete_agent(**kwargs: Any) -> Any:
    """执行 Agent 推理；业务层无需感知模型名、供应商或密钥。"""
    settings = get_settings()
    return _completion(
        model=settings.agent_model,
        timeout=settings.agent_timeout_seconds,
        **kwargs,
    )


def get_agent_completion() -> Callable[..., Any]:
    """返回可注入 Agent 循环的模型调用函数，并提前检查配置。"""
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY（.env）")
    return complete_agent


def extract_json(system_prompt: str, user_content: str) -> str:
    """执行简历结构化提取并返回模型生成的 JSON 文本。"""
    settings = get_settings()
    response = _completion(
        model=settings.normalization_model,
        timeout=settings.normalization_timeout_seconds,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("模型返回了空内容")
    return content
