from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.datetime_format import utc_seconds_isoformat


class DisruptionRead(BaseModel):
    category: str | None
    additional_info: str | None


class LineStatusRead(BaseModel):
    status_severity: int
    status_severity_description: str
    reason: str | None
    disruption: DisruptionRead | None


class LineStatusTransition(StrEnum):
    BASELINE = "baseline"
    DISRUPTION_STARTED = "disruption_started"
    DISRUPTION_CHANGED = "disruption_changed"
    SERVICE_RESUMED = "service_resumed"
    STATUS_CHANGED = "status_changed"


class LineStatusSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: str
    observed_at: datetime
    transition: LineStatusTransition
    statuses: list[LineStatusRead]

    @field_validator("observed_at", mode="after")
    @classmethod
    def mark_sqlite_timestamps_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @field_serializer("observed_at", when_used="json")
    def serialize_observed_at(self, value: datetime) -> str:
        return utc_seconds_isoformat(value)


class DailyTimelineRead(BaseModel):
    line_id: str
    operational_date: date
    timezone: str
    starts_at: datetime
    ends_at: datetime
    snapshots: list[LineStatusSnapshotRead]


class DailyDisruptionSummaryRead(BaseModel):
    operational_date: date
    timezone: str
    starts_at: datetime
    ends_at: datetime
    lines: dict[str, list[LineStatusSnapshotRead]]
