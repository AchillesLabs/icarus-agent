"""Add tenant_api_tokens table for dynamic API tokens, SHA-256 hashes, and revocation.

Revision ID: 0005_tenant_api_tokens
Revises: 0004_scheduled_jobs
Create Date: 2026-10-19 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_tenant_api_tokens"
down_revision: str | None = "0004_scheduled_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_api_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenant_api_tokens_owner_id", "tenant_api_tokens", ["owner_id"])
    op.create_index(
        "ix_tenant_api_tokens_token_hash", "tenant_api_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_tenant_api_tokens_revoked_at", "tenant_api_tokens", ["revoked_at"])


def downgrade() -> None:
    op.drop_table("tenant_api_tokens")
