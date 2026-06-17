"""Add worker runs

Revision ID: 20260617_0002
Revises: 20260617_0001
Create Date: 2026-06-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0002"
down_revision: str | Sequence[str] | None = "20260617_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("worker_name", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_runs_status", "worker_runs", ["status"], unique=False)
    op.create_index(
        "ix_worker_runs_worker_name",
        "worker_runs",
        ["worker_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_worker_runs_worker_name", table_name="worker_runs")
    op.drop_index("ix_worker_runs_status", table_name="worker_runs")
    op.drop_table("worker_runs")
