from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[3]
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    model_api_key: str = Field(min_length=1)
    model_base_url: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    rerank_model: str = Field(min_length=1)

    knowledge_data_dir: Path = SERVICE_ROOT / "data"
    knowledge_wiki_dir: Path = SERVICE_ROOT / "data" / "wiki"
    knowledge_chunk_size: int = Field(default=550, ge=100)
    knowledge_chunk_overlap: int = Field(default=80, ge=0)
    knowledge_rough_top_k: int = Field(default=15, ge=1, le=100)
    knowledge_final_top_k: int = Field(default=3, ge=1, le=20)
    knowledge_refusal_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    embedding_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        validation_alias=AliasChoices(
            "EMBEDDING_TIMEOUT_SECONDS", "MODEL_TIMEOUT_SECONDS"
        ),
    )
    rerank_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        validation_alias=AliasChoices("RERANK_TIMEOUT_SECONDS", "MODEL_TIMEOUT_SECONDS"),
    )

    @field_validator("knowledge_data_dir", "knowledge_wiki_dir", mode="after")
    @classmethod
    def resolve_service_path(cls, value: Path) -> Path:
        """让根目录 .env 中的数据路径仍相对于 knowledge 服务目录。"""
        return value if value.is_absolute() else (SERVICE_ROOT / value).resolve()

    @property
    def chroma_dir(self) -> Path:
        return self.knowledge_data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()

