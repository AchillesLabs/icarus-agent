"""Add tenant_credentials table for encrypted server-side BYOK provider keys.

Revision ID: 0006_tenant_credentials
Revises: 0005_tenant_api_tokens
Create Date: 2026-10-19 10:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_tenant_credentials"
down_revision: str | None = "0005_tenant_api_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "provider", name="uq_tenant_credentials_owner_provider"),
    )
    op.create_index("ix_tenant_credentials_owner_id", "tenant_credentials", ["owner_id"])
    op.create_index("ix_tenant_credentials_provider", "tenant_credentials", ["provider"])


def downgrade() -> None:
    op.drop_table("tenant_credentials")
