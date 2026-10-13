"""PostgreSQL engine and database session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.db.base import Base

_settings = get_settings()
_settings.data_dir.mkdir(parents=True, exist_ok=True)
_settings.upload_dir.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


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
