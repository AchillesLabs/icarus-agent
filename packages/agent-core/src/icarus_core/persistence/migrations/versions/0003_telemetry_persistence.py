"""Add indexes for token estimates and run execution status.

Revision ID: 0003_telemetry_persistence
Revises: 0002_tool_persistence
Create Date: 2026-10-18 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_telemetry_persistence"
down_revision: str | None = "0002_tool_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_messages_token_estimate", "messages", ["token_estimate"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_messages_token_estimate", table_name="messages")
