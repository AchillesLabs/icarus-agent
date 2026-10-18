"""Add tool persistence columns to messages table.

Revision ID: 0002_tool_persistence
Revises: 0001_initial_schema
Create Date: 2026-10-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_tool_persistence"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("tool_calls", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("tool_call_id", sa.String(length=128), nullable=True))
    op.add_column("messages", sa.Column("name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "name")
    op.drop_column("messages", "tool_call_id")
    op.drop_column("messages", "tool_calls")
