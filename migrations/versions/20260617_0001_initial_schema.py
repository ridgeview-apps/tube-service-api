"""Initial schema

Revision ID: 20260617_0001
Revises:
Create Date: 2026-06-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "line_status_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_snapshot_line_observed",
        "line_status_snapshots",
        ["line_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "notification_devices",
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("push_token", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index(
        "ix_notification_devices_push_token",
        "notification_devices",
        ["push_token"],
        unique=True,
    )

    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("line_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("status_description", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_events_dedupe_key",
        "notification_events",
        ["dedupe_key"],
        unique=True,
    )
    op.create_index(
        "ix_notification_events_line_id",
        "notification_events",
        ["line_id"],
        unique=False,
    )

    op.create_table(
        "line_statuses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("status_severity", sa.Integer(), nullable=False),
        sa.Column("status_description", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("disruption_category", sa.String(length=64), nullable=True),
        sa.Column("additional_info", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["line_status_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_line_statuses_snapshot_id",
        "line_statuses",
        ["snapshot_id"],
        unique=False,
    )

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

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("push_token", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=256), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["notification_events.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "device_id",
            name="uq_notification_delivery_event_device",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_device_id",
        "notification_deliveries",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_event_id",
        "notification_deliveries",
        ["event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_event_id",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_device_id",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
    op.drop_index("ix_line_statuses_snapshot_id", table_name="line_statuses")
    op.drop_table("line_statuses")
    op.drop_index("ix_notification_events_line_id", table_name="notification_events")
    op.drop_index("ix_notification_events_dedupe_key", table_name="notification_events")
    op.drop_table("notification_events")
    op.drop_index("ix_notification_devices_push_token", table_name="notification_devices")
    op.drop_table("notification_devices")
    op.drop_index("ix_snapshot_line_observed", table_name="line_status_snapshots")
    op.drop_table("line_status_snapshots")
