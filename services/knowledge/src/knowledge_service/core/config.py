from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    model_api_key: str = Field(min_length=1)
    model_base_url: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    rerank_model: str = Field(min_length=1)

    knowledge_data_dir: Path = SERVICE_ROOT / "data"
    knowledge_chunk_size: int = Field(default=550, ge=100)
    knowledge_chunk_overlap: int = Field(default=80, ge=0)
    knowledge_rough_top_k: int = Field(default=15, ge=1, le=100)
    knowledge_final_top_k: int = Field(default=3, ge=1, le=20)
    knowledge_refusal_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    model_timeout_seconds: float = Field(default=120.0, gt=0)

    @property
    def chroma_dir(self) -> Path:
        return self.knowledge_data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()

