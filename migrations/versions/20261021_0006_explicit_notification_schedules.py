"""Replace notification schedule presets with explicit rules.

Revision ID: 20261021_0006
Revises: 20261016_0005
Create Date: 2026-10-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0006"
down_revision: str | Sequence[str] | None = "20261016_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
_ALL_DAYS = [*_WEEKDAYS, "sat", "sun"]


def _explicit_schedules(
    schedule_preset: str,
    custom_schedules: list[dict[str, object]],
) -> list[dict[str, object]]:
    match schedule_preset:
        case "anytime":
            return [{"days": _ALL_DAYS, "all_day": True, "windows": []}]
        case "weekday_all_day":
            return [{"days": _WEEKDAYS, "all_day": True, "windows": []}]
        case "weekends":
            return [{"days": ["sat", "sun"], "all_day": True, "windows": []}]
        case "weekday_peak":
            return [
                {
                    "days": _WEEKDAYS,
                    "all_day": False,
                    "windows": [
                        {"start_time": "06:30:00", "end_time": "09:30:00"},
                        {"start_time": "16:00:00", "end_time": "19:00:00"},
                    ],
                }
            ]
        case "custom":
            return [
                {
                    "days": schedule["days"],
                    "all_day": False,
                    "windows": [
                        {
                            "start_time": schedule["start_time"],
                            "end_time": schedule["end_time"],
                        }
                    ],
                }
                for schedule in custom_schedules
            ]
        case _:
            raise ValueError(f"Unsupported notification schedule preset: {schedule_preset}")


def upgrade() -> None:
    op.add_column(
        "notification_line_preferences",
        sa.Column("schedules", sa.JSON(), nullable=True),
    )

    connection = op.get_bind()
    preferences = sa.table(
        "notification_line_preferences",
        sa.column("device_id", sa.String()),
        sa.column("line_id", sa.String()),
        sa.column("schedule_preset", sa.String()),
        sa.column("custom_schedules", sa.JSON()),
        sa.column("schedules", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(
            preferences.c.device_id,
            preferences.c.line_id,
            preferences.c.schedule_preset,
            preferences.c.custom_schedules,
        )
    ).mappings()
    for row in rows:
        connection.execute(
            preferences.update()
            .where(preferences.c.device_id == row["device_id"])
            .where(preferences.c.line_id == row["line_id"])
            .values(
                schedules=_explicit_schedules(
                    row["schedule_preset"],
                    row["custom_schedules"] or [],
                )
            )
        )

    with op.batch_alter_table("notification_line_preferences") as batch_op:
        batch_op.alter_column("schedules", nullable=False)
        batch_op.drop_column("custom_schedules")
        batch_op.drop_column("schedule_preset")


def downgrade() -> None:
    with op.batch_alter_table("notification_line_preferences") as batch_op:
        batch_op.add_column(sa.Column("schedule_preset", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("custom_schedules", sa.JSON(), nullable=True))

    connection = op.get_bind()
    preferences = sa.table(
        "notification_line_preferences",
        sa.column("device_id", sa.String()),
        sa.column("line_id", sa.String()),
        sa.column("schedule_preset", sa.String()),
        sa.column("custom_schedules", sa.JSON()),
        sa.column("schedules", sa.JSON()),
    )
    rows = connection.execute(
        sa.select(preferences.c.device_id, preferences.c.line_id, preferences.c.schedules)
    ).mappings()
    for row in rows:
        schedules = row["schedules"] or []
        custom_schedules = [
            {"days": schedule["days"], **window}
            for schedule in schedules
            for window in schedule.get("windows", [])
        ]
        schedule_preset = "custom" if custom_schedules else "anytime"
        connection.execute(
            preferences.update()
            .where(preferences.c.device_id == row["device_id"])
            .where(preferences.c.line_id == row["line_id"])
            .values(
                schedule_preset=schedule_preset,
                custom_schedules=custom_schedules,
            )
        )

    with op.batch_alter_table("notification_line_preferences") as batch_op:
        batch_op.alter_column("schedule_preset", nullable=False)
        batch_op.alter_column("custom_schedules", nullable=False)
        batch_op.drop_column("schedules")
