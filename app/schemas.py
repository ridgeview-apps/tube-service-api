from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class HealthResponse(BaseModel):
    status: str


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: str
    line_name: str
    mode_name: str
    status_severity: int
    status_description: str
    reason: str | None
    observed_at: datetime

    @field_validator("observed_at", mode="after")
    @classmethod
    def mark_sqlite_timestamps_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class DailyHistoryResponse(BaseModel):
    line_id: str
    date: date
    timezone: str
    snapshots: list[SnapshotResponse]
