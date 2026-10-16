"""Declarative Base（独立模块，避免 session <-> models 循环导入）。"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
