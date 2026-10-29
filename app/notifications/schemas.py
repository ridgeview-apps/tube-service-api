from datetime import datetime, time
from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_serializer,
    field_validator,
    model_validator,
)

from app.datetime_format import utc_seconds_isoformat
from app.line_status.lines import SUPPORTED_LINE_IDS


class PushPlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


class NotificationSeverityThreshold(StrEnum):
    MINOR_DELAYS = "minor_delays"
    SEVERE_DELAYS = "severe_delays"
    SUSPENDED = "suspended"


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class NotificationScheduleWindow(BaseModel):
    start_time: Annotated[
        time,
        WithJsonSchema(
            {
                "type": "string",
                "pattern": r"^\d{2}:\d{2}$",
                "description": "Always returned in HH:mm format.",
                "examples": ["06:30"],
            },
            mode="serialization",
        ),
    ] = Field(
        description=(
            "A local time. Send HH:mm; seconds are accepted and discarded. "
            "Always returned in HH:mm format."
        )
    )
    end_time: Annotated[
        time,
        WithJsonSchema(
            {
                "type": "string",
                "pattern": r"^\d{2}:\d{2}$",
                "description": "Always returned in HH:mm format.",
                "examples": ["09:30"],
            },
            mode="serialization",
        ),
    ] = Field(
        description=(
            "A local time. Send HH:mm; seconds are accepted and discarded. "
            "Always returned in HH:mm format."
        )
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def remove_seconds(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0)

    @model_validator(mode="after")
    def require_forward_time_window(self) -> "NotificationScheduleWindow":
        if self.start_time >= self.end_time:
            raise ValueError("Schedule start_time must be before end_time")
        return self

    @field_serializer("start_time", "end_time", when_used="json")
    def serialize_time(self, value: time) -> str:
        return value.strftime("%H:%M")


class NotificationSchedule(BaseModel):
    days: list[Weekday] = Field(min_length=1)
    all_day: bool = False
    windows: list[NotificationScheduleWindow] = Field(default_factory=list)

    @field_validator("days")
    @classmethod
    def deduplicate_days(cls, value: list[Weekday]) -> list[Weekday]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def require_all_day_or_windows(self) -> "NotificationSchedule":
        if self.all_day and self.windows:
            raise ValueError("all_day schedules cannot include windows")
        if not self.all_day and not self.windows:
            raise ValueError("Schedules must be all_day or include at least one window")
        return self


class NotificationDeviceRegistration(BaseModel):
    platform: PushPlatform
    push_token: str = Field(min_length=1, max_length=512)
    app_version: str | None = Field(default=None, max_length=64)
    app_variant: str = Field(default="production", min_length=1, max_length=64)


class NotificationDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    platform: PushPlatform
    enabled: bool
    app_version: str | None
    app_variant: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime

    @field_serializer("created_at", "updated_at", "last_seen_at", when_used="json")
    def serialize_timestamps(self, value: datetime) -> str:
        return utc_seconds_isoformat(value)


class NotificationLinePreferenceUpdate(BaseModel):
    enabled: bool = True
    line_id: str
    severity_threshold: NotificationSeverityThreshold = NotificationSeverityThreshold.MINOR_DELAYS
    notify_recoveries: bool = True
    schedules: list[NotificationSchedule] = Field(min_length=1)

    @field_validator("line_id", mode="before")
    @classmethod
    def normalize_line_id(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @field_validator("line_id")
    @classmethod
    def validate_line_id(cls, value: str) -> str:
        if value not in SUPPORTED_LINE_IDS:
            raise ValueError(f"Unsupported line ID: {value}")
        return value


class NotificationLinePreferencePatch(BaseModel):
    """The mutable fields of a line preference in a merge-patch request."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    severity_threshold: NotificationSeverityThreshold | None = None
    notify_recoveries: bool | None = None
    schedules: list[NotificationSchedule] | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def reject_null_fields(self) -> "NotificationLinePreferencePatch":
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Line preference fields cannot be null")
        return self


class NotificationPreferencesBase(BaseModel):
    timezone: str = "Europe/London"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Invalid timezone") from error
        return value


class NotificationPreferencesUpdate(NotificationPreferencesBase):
    lines: list[NotificationLinePreferenceUpdate] = Field(default_factory=list)

    @field_validator("lines")
    @classmethod
    def require_unique_line_ids(
        cls,
        value: list[NotificationLinePreferenceUpdate],
    ) -> list[NotificationLinePreferenceUpdate]:
        line_ids = [line.line_id for line in value]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("Duplicate line IDs are not allowed")
        return value


class NotificationPreferencesPatch(BaseModel):
    """RFC 7396 patch document for the per-line preference collection."""

    model_config = ConfigDict(extra="forbid")

    lines: dict[str, NotificationLinePreferencePatch | None] = Field(default_factory=dict)

    @field_validator("lines")
    @classmethod
    def normalize_and_validate_line_ids(
        cls,
        value: dict[str, NotificationLinePreferencePatch | None],
    ) -> dict[str, NotificationLinePreferencePatch | None]:
        normalized: dict[str, NotificationLinePreferencePatch | None] = {}
        for line_id, patch in value.items():
            normalized_line_id = line_id.lower()
            if normalized_line_id not in SUPPORTED_LINE_IDS:
                raise ValueError(f"Unsupported line ID: {normalized_line_id}")
            if normalized_line_id in normalized:
                raise ValueError("Duplicate normalized line IDs are not allowed")
            normalized[normalized_line_id] = patch
        return normalized


class NotificationLinePreferenceRead(NotificationLinePreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)


class NotificationPreferencesRead(NotificationPreferencesBase):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    lines: list[NotificationLinePreferenceRead]
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_timestamps(self, value: datetime) -> str:
        return utc_seconds_isoformat(value)


class NotificationTestPushRead(BaseModel):
    delivery_id: int
    device_id: str
    status: str
    provider_message_id: str | None = None
    failure_reason: str | None = None
