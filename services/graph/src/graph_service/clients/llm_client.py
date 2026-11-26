"""图谱服务模型客户端：封装 LiteLLM，业务层只拿到模型输出的 JSON 文本。"""

from litellm import completion as litellm_completion

from graph_service.core.config import Settings


class LLMConfigError(RuntimeError):
    """模型配置缺失（密钥、网关地址或模型名未配置）。"""


class LLMResponseError(RuntimeError):
    """模型返回了空内容，无法继续解析。"""


def _litellm_model(model: str) -> str:
    # 没有 "/" 的模型名按 OpenAI 兼容网关处理，与 app 服务口径一致
    return model if "/" in model else f"openai/{model}"


def chat_json(
    settings: Settings,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
) -> str:
    """调用模型，返回模型输出的 JSON 字符串。

    配置由调用方传入（不在函数内部读取全局配置），便于测试与多配置并存。
    schema 必传：通过接口参数强制约束输出结构。
    只负责"调一次、拿到文本"：JSON Schema / Pydantic 校验与重试由 services 层负责。
    模型调用本身的异常（超时、网络、服务商拒绝 Schema 等）原样抛出，不吞。

    Raises:
        LLMConfigError: 密钥、网关地址、模型名任一未配置（调用前检查，不会发出请求）。
        LLMResponseError: 模型返回空内容或只有空白字符。
    """
    # 强制显式配置：缺哪个就报哪个。网关地址也必须配置，否则请求会落到 litellm 的
    # 默认地址（官方 OpenAI），把别家的密钥发到不该发的地方。
    if not settings.llm_api_key:
        raise LLMConfigError("未配置 LLM_API_KEY（.env）")
    if not settings.llm_base_url:
        raise LLMConfigError("未配置 LLM_BASE_URL（.env）")
    if not settings.graph_llm_model:
        raise LLMConfigError("未配置 GRAPH_LLM_MODEL（.env）")

    response = litellm_completion(
        model=_litellm_model(settings.graph_llm_model),
        api_key=settings.llm_api_key,
        api_base=settings.llm_base_url.rstrip("/"),
        timeout=settings.graph_llm_timeout_seconds,
        num_retries=0,  # 重试放在我们自己的逻辑里，这里不重试
        temperature=0,  # 抽取任务要稳定输出
        # 接口强制约束：Schema 放进接口参数，由服务端按它约束生成。
        # strict 在 json_schema 对象内部，与 name、schema 同层（阿里云文档原文的写法）。
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "extraction_result", "strict": True, "schema": schema},
        },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise LLMResponseError("模型返回了空内容")
    return content
