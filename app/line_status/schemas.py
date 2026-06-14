from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class LineStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status_severity: int
    status_description: str
    reason: str | None
    disruption_category: str | None
    additional_info: str | None


class LineStatusSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: str
    observed_at: datetime
    statuses: list[LineStatusRead]

    @field_validator("observed_at", mode="after")
    @classmethod
    def mark_sqlite_timestamps_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class DailyTimelineRead(BaseModel):
    line_id: str
    date: date
    timezone: str
    snapshots: list[LineStatusSnapshotRead]


class LineDisruptionSummaryRead(BaseModel):
    line_id: str
    disrupted: bool
    disruption_count: int
    latest_disruption_at: datetime | None

    @field_validator("latest_disruption_at", mode="after")
    @classmethod
    def mark_sqlite_disruption_timestamps_as_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)
