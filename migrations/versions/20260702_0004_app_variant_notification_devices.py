"""Add app variant to notification devices

Revision ID: 20260702_0004
Revises: 20260622_0003
Create Date: 2026-07-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_0004"
down_revision: str | Sequence[str] | None = "20260622_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_devices",
        sa.Column(
            "app_variant",
            sa.String(length=64),
            nullable=False,
            server_default="production",
        ),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "app_variant",
            sa.String(length=64),
            nullable=False,
            server_default="production",
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_deliveries", "app_variant")
    op.drop_column("notification_devices", "app_variant")
