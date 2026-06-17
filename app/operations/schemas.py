from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class WorkerRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_name: str
    started_at: datetime
    finished_at: datetime
    status: str
    processed_count: int
    error_message: str | None

    @field_validator("started_at", "finished_at", mode="after")
    @classmethod
    def mark_sqlite_timestamps_as_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class WorkerRunsRead(BaseModel):
    workers: dict[str, WorkerRunRead]
