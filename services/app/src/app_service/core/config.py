"""环境配置：路径、大模型密钥、超时与重试参数。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 存储 ---
    # 相对当前工作目录：开发时从仓库根运行、容器内 WORKDIR=/app，
    # 各自落在其下的 data/；可用 DATA_DIR / UPLOAD_DIR 环境变量覆盖。
    data_dir: Path = Path("data")
    upload_dir: Path = Path("data") / "uploads"
    database_url: str

    # --- 上传约束（PRD：仅 PDF，单文件 <5M）---
    max_upload_size_mb: int = 10

    # --- 本服务的模型任务（底层协议统一由 clients/model_client.py 封装）---
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    normalization_model: str = Field(
        default="qwen-plus",
        validation_alias=AliasChoices("NORMALIZATION_MODEL", "LLM_MODEL"),
    )
    normalization_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        validation_alias=AliasChoices(
            "NORMALIZATION_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"
        ),
    )
    agent_model: str = Field(
        default="qwen-plus",
        validation_alias=AliasChoices("AGENT_MODEL", "LLM_MODEL"),
    )
    agent_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        validation_alias=AliasChoices("AGENT_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"),
    )
    max_llm_retries: int = 2  # SPEC：校验失败最多重试 2 次

    # --- 招聘 Agent / Text2SQL ---
    agent_max_result_rows: int = 50
    agent_sql_timeout_ms: int = 3000
    agent_llm_max_retries: int = 2
    agent_llm_retry_backoff_seconds: float = 0.5

    # --- 解析服务（PDF -> 文本，独立微服务）---
    # 解析与 OCR 均由解析服务承担；本服务不再本地解析。
    parser_service_base_url: str = "http://127.0.0.1:8002"
    parser_http_connect_timeout_seconds: float = 5.0
    parser_http_read_timeout_seconds: float = 120.0  # OCR 逐页视觉调用较慢，须远大于模型超时
    parser_http_max_retries: int = 1  # 解析幂等，仅对连接失败/服务异常重试
    parser_http_retry_backoff_seconds: float = 1.0

    # --- 知识库服务（Wiki 卡片 -> 切片与向量索引）---
    knowledge_service_base_url: str = "http://127.0.0.1:8001"
    knowledge_http_connect_timeout_seconds: float = 5.0
    knowledge_http_read_timeout_seconds: float = 120.0
    knowledge_http_max_retries: int = 1
    knowledge_http_retry_backoff_seconds: float = 1.0

    # --- HR 用户（登录会话鉴权；hr_id 在无显式用户时透传）---
    default_hr_id: str = "hr_admin"

    auth_session_hours: int = 8
    # 首次启动 seed 管理员账号 hr_admin 用的初始密码（仅空表时创建一次）
    auth_admin_password: str = "Resume@2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()
