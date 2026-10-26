"""Rename talent_pool.knowledge_document_id to knowledge_talent_card_id.

Rename companion of the document_id -> talent_card_id naming sweep:
the column stores the knowledge-service card key (talent-{pool_id}).

Revision ID: 20261023_0003
Revises: 20261022_0002
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261023_0003"
down_revision: str | None = "20261022_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE talent_pool RENAME COLUMN knowledge_document_id"
        " TO knowledge_talent_card_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE talent_pool RENAME COLUMN knowledge_talent_card_id"
        " TO knowledge_document_id"
    )
