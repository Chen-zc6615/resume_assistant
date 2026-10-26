"""Persist Agent intent, trace identifier and execution metrics.

Revision ID: 20261023_0005
Revises: 20261023_0004
Create Date: 2026-10-23
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0005"
down_revision: str | None = "20261023_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_messages", sa.Column("intent", sa.String(50), nullable=True))
    op.add_column("agent_messages", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column(
        "agent_messages",
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_agent_messages_trace_id", "agent_messages", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_messages_trace_id", table_name="agent_messages")
    op.drop_column("agent_messages", "metrics")
    op.drop_column("agent_messages", "trace_id")
    op.drop_column("agent_messages", "intent")
