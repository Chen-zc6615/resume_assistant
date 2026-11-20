from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 约定：命令从仓库根目录运行，读取根目录 .env；容器内配置由 compose 注入
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    # 全仓库唯一一组模型网关凭据（OpenAI 兼容），与 app/knowledge 共用
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ocr_model: str = "qwen-vl-max"
    max_upload_size_mb: int = Field(default=5, ge=1, le=50)
    min_effective_chars: int = Field(default=50, ge=1)
    ocr_max_retries: int = Field(default=2, ge=1, le=5)
    ocr_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        validation_alias=AliasChoices("OCR_TIMEOUT_SECONDS", "PARSE_TIMEOUT_SECONDS"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

