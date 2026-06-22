"""Add per-line notification preferences

Revision ID: 20260622_0003
Revises: 20260617_0002
Create Date: 2026-06-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0003"
down_revision: str | Sequence[str] | None = "20260617_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("notification_preferences")
    op.create_table(
        "notification_preferences",
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["notification_devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_table(
        "notification_line_preferences",
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("line_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("severity_threshold", sa.String(length=32), nullable=False),
        sa.Column("notify_recoveries", sa.Boolean(), nullable=False),
        sa.Column("schedule_preset", sa.String(length=32), nullable=False),
        sa.Column("custom_schedules", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["notification_preferences.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id", "line_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_line_preferences")
    op.drop_table("notification_preferences")
    op.create_table(
        "notification_preferences",
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("line_ids", sa.JSON(), nullable=False),
        sa.Column("severity_threshold", sa.String(length=32), nullable=False),
        sa.Column("notify_recoveries", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("schedule_preset", sa.String(length=32), nullable=False),
        sa.Column("custom_schedules", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["notification_devices.device_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
