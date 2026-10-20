"""Add integration_connections and oauth_states tables, and enable PostgreSQL Row Level Security.

Revision ID: 0007_integrations_and_rls
Revises: 0006_tenant_credentials
Create Date: 2026-10-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_integrations_and_rls"
down_revision: str | None = "0006_tenant_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create integration_connections table
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="disconnected"),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(length=32), nullable=True, server_default="Bearer"),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "provider", name="uq_integration_connections_owner_provider"
        ),
    )
    op.create_index("ix_integration_connections_owner_id", "integration_connections", ["owner_id"])
    op.create_index("ix_integration_connections_provider", "integration_connections", ["provider"])

    # 2. Create oauth_states table for PKCE & state verification
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=True),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_states_state", "oauth_states", ["state"], unique=True)
    op.create_index("ix_oauth_states_owner_id", "oauth_states", ["owner_id"])

    # 3. PostgreSQL Row-Level Security (RLS) enforcement
    bind = op.get_bind()
    if bind and bind.dialect.name == "postgresql":
        rls_tables = [
            "sessions",
            "messages",
            "agent_runs",
            "tenant_credentials",
            "tenant_api_tokens",
            "integration_connections",
            "oauth_states",
        ]
        for tbl in rls_tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(
                f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING (owner_id = current_setting('app.current_tenant', true));"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind and bind.dialect.name == "postgresql":
        rls_tables = [
            "sessions",
            "messages",
            "agent_runs",
            "tenant_credentials",
            "tenant_api_tokens",
            "integration_connections",
            "oauth_states",
        ]
        for tbl in rls_tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    op.drop_table("oauth_states")
    op.drop_table("integration_connections")
