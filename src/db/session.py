"""SQLite 引擎（WAL 模式）与会话管理。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.db.base import Base

_settings = get_settings()
_settings.data_dir.mkdir(parents=True, exist_ok=True)
_settings.upload_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _settings.sqlalchemy_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_wal(dbapi_connection, _record) -> None:
    """PRD 选型：SQLite WAL 模式（读写并发更友好）。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。"""
    Base.metadata.create_all(bind=engine)
