"""Add per-line notification disruption state

Revision ID: 20261016_0005
Revises: 20260702_0004
Create Date: 2026-10-16 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_0005"
down_revision: str | Sequence[str] | None = "20260702_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_line_disruption_states",
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("line_id", sa.String(length=64), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["notification_devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", "line_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_line_disruption_states")
