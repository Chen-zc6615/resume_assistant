from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 约定：命令从仓库根目录运行，读取根目录 .env；容器内配置由 compose 注入
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = Field(min_length=8)
    neo4j_database: str = "neo4j"
    neo4j_connection_timeout_seconds: float = Field(default=5.0, gt=0)

    llm_api_key: str = ""
    llm_base_url: str = ""
    graph_llm_model: str = ""
    graph_llm_timeout_seconds: float = Field(default=60.0, gt=0)
    graph_extract_max_retries: int = Field(default=1, ge=0, le=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # 字段由环境变量 / .env 注入
