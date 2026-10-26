"""Merge resume_profiles primary key into resume_id (FK-PK, 1:1).

Drop the surrogate profile_id: resume_profiles.resume_id becomes the
primary key (one resume, exactly one profile). Child tables (skills,
education, work, project) and filter_results re-point to resume_id.

依赖顺序（PostgreSQL 的 FK 绑定到具体约束对象，删除被依赖的约束
会被拒绝，因此切换必须分五步走）：
  1. 子表先断开旧 FK（profile_id → 画像表 profile_id PK）
  2. 画像表主键真空切换（此刻无任何 FK 指向它）
  3. 子表补 resume_id 数据并挂新 FK（绑定新主键）
  4. filter_results 删除冗余的 profile_id 列
  5. 画像表删除 profile_id 列

Revision ID: 20261023_0004
Revises: 20261023_0003
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261023_0004"
down_revision: str | None = "20261023_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHILD_TABLES = ("profile_skills", "education_experiences", "work_experiences", "project_experiences")


def upgrade() -> None:
    # 1. 断开全部旧 FK（四张经历子表 + filter_results；列暂留，仅卸下约束）
    for table in (*_CHILD_TABLES, "filter_results"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_profile_id_fkey")

    # 2. 画像表主键真空切换：此刻无人依赖，任意顺序安全
    op.execute("ALTER TABLE resume_profiles DROP CONSTRAINT resume_profiles_pkey")
    op.execute("ALTER TABLE resume_profiles DROP CONSTRAINT resume_profiles_resume_id_key")
    op.execute("ALTER TABLE resume_profiles ADD PRIMARY KEY (resume_id)")

    # 3. 子表补 resume_id 数据并挂新 FK（PG 绑定到新主键）
    for table in _CHILD_TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN resume_id BIGINT")
        op.execute(
            f"UPDATE {table} t SET resume_id = p.resume_id"
            f" FROM resume_profiles p WHERE p.profile_id = t.profile_id"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN resume_id SET NOT NULL")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_resume_id_fkey"
            f" FOREIGN KEY (resume_id) REFERENCES resume_profiles(resume_id)"
        )
        op.execute(f"ALTER TABLE {table} DROP COLUMN profile_id")

    # 4. filter_results 已断 FK，仅删冗余列（本就有 resume_id 指向 resumes）
    op.execute("ALTER TABLE filter_results DROP COLUMN profile_id")

    # 5. 画像表删除 profile_id（已无任何引用）
    op.execute("ALTER TABLE resume_profiles DROP COLUMN profile_id")


def downgrade() -> None:
    raise NotImplementedError(
        "回退需重建代理主键 profile_id 并回填子表，"
        "项目初期请直接重建数据库（docker compose down -v 后重跑迁移）"
    )
