"""Add persistent Agent tasks, messages and approval actions.

Revision ID: 20261022_0002
Revises: 20261018_0001
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261022_0002"
down_revision: str | None = "20261018_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tasks (
            task_id BIGSERIAL PRIMARY KEY,
            title VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_by VARCHAR(50) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_agent_tasks_status CHECK (status IN ('active', 'archived'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            message_id BIGSERIAL PRIMARY KEY,
            task_id BIGINT NOT NULL REFERENCES agent_tasks (task_id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            tool_traces JSON NOT NULL DEFAULT '[]'::json,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_agent_messages_role CHECK (role IN ('user', 'assistant'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_actions (
            action_id BIGSERIAL PRIMARY KEY,
            task_id BIGINT NOT NULL REFERENCES agent_tasks (task_id) ON DELETE CASCADE,
            action_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            payload JSON NOT NULL DEFAULT '{}'::json,
            result JSON,
            decision_reason TEXT,
            decided_by VARCHAR(50),
            decided_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_agent_actions_status
                CHECK (status IN ('pending', 'approved', 'rejected', 'executed', 'failed'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_messages_task_id ON agent_messages (task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_actions_task_id ON agent_actions (task_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_actions")
    op.execute("DROP TABLE IF EXISTS agent_messages")
    op.execute("DROP TABLE IF EXISTS agent_tasks")
