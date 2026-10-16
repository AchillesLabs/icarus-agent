"""Initial database schema for sessions, messages, and agent runs.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-16 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("mode", sa.String(length=64), nullable=False, server_default="chat"),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Session"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_sessions_owner_id", "sessions", ["owner_id"])

    # 2. Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_owner_id", "messages", ["owner_id"])

    # 3. Create agent_runs table
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("budget_counters", sa.JSON(), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_owner_id", "agent_runs", ["owner_id"])
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])
    op.create_index("ix_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_table("messages")
    op.drop_table("sessions")
