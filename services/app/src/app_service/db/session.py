"""PostgreSQL engine and database session management."""

from __future__ import annotations

from collections.abc import Generator  #生成器
from sqlalchemy import create_engine  #创建数据库引擎
from sqlalchemy.orm import Session, sessionmaker  #session，一次和数据库的对话， sessionmaker会话工厂
from app_service.core.config import get_settings
from app_service.db.base import Base

_settings = get_settings()  #获取配置
_settings.data_dir.mkdir(parents=True, exist_ok=True)
_settings.upload_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(_settings.database_url, pool_pre_ping=True)  #创建引擎
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)  #生产数据库会话的工具


def get_db() -> Generator[Session, None, None]:
    """Provide one database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create database tables that do not already exist."""
    Base.metadata.create_all(bind=engine)