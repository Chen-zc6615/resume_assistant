"""环境配置：路径、大模型密钥、超时与重试参数。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：src/core/config.py -> 上两级
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        """`.env` 文件优先于进程环境变量。

        默认顺序是环境变量 > .env，但 IDE/终端里残留的旧环境变量
        会静默劫持配置（曾导致有效 key 被 67 位旧值覆盖）。
        团队约定：密钥以 .env 为唯一真理源。
        """
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    # --- 存储 ---
    data_dir: Path = BASE_DIR / "data"
    db_path: Path = BASE_DIR / "data" / "smartresume.db"
    upload_dir: Path = BASE_DIR / "data" / "uploads"

    # --- 上传约束（PRD：仅 PDF，单文件 <5M）---
    max_upload_size_mb: int = 5
    min_effective_chars: int = 50  # SPEC：解析文本有效字符数 ≥ 50 才进入归一化

    # --- 大模型（DashScope OpenAI 兼容）---
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"          # 归一化结构化提取
    ocr_model: str = "qwen-vl-max"        # 扫描件 OCR 兜底
    llm_timeout_seconds: float = 20.0     # PRD：归一化超 20s 判失败
    parse_timeout_seconds: float = 10.0   # PRD：单份解析超 10s 重试
    max_llm_retries: int = 2             # SPEC：校验失败最多重试 2 次
    max_ocr_retries: int = 2

    # --- HR 用户（MVP 无登录，透传）---
    default_hr_id: str = "hr_admin"

    @property
    def sqlalchemy_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
