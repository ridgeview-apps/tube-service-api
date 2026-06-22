from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.line_status.lines import SUPPORTED_LINE_IDS


class PushPlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


class NotificationSeverityThreshold(StrEnum):
    MINOR_DELAYS = "minor_delays"
    SEVERE_DELAYS = "severe_delays"
    SUSPENDED = "suspended"


class NotificationSchedulePreset(StrEnum):
    ANYTIME = "anytime"
    WEEKDAY_PEAK = "weekday_peak"
    WEEKDAY_ALL_DAY = "weekday_all_day"
    WEEKENDS = "weekends"
    CUSTOM = "custom"


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class NotificationScheduleWindow(BaseModel):
    days: list[Weekday] = Field(min_length=1)
    start_time: time
    end_time: time

    @field_validator("days")
    @classmethod
    def deduplicate_days(cls, value: list[Weekday]) -> list[Weekday]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def require_forward_time_window(self) -> "NotificationScheduleWindow":
        if self.start_time >= self.end_time:
            raise ValueError("Schedule start_time must be before end_time")
        return self


class NotificationDeviceRegistration(BaseModel):
    platform: PushPlatform
    push_token: str = Field(min_length=1, max_length=512)
    app_version: str | None = Field(default=None, max_length=64)


class NotificationDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    platform: PushPlatform
    enabled: bool
    app_version: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime


class NotificationLinePreferenceUpdate(BaseModel):
    enabled: bool = True
    line_id: str
    severity_threshold: NotificationSeverityThreshold = NotificationSeverityThreshold.MINOR_DELAYS
    notify_recoveries: bool = True
    schedule_preset: NotificationSchedulePreset = NotificationSchedulePreset.WEEKDAY_PEAK
    custom_schedules: list[NotificationScheduleWindow] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def require_custom_schedules_for_custom_preset(self) -> "NotificationLinePreferenceUpdate":
        if self.schedule_preset == NotificationSchedulePreset.CUSTOM and not self.custom_schedules:
            raise ValueError("custom_schedules is required for the custom preset")
        if self.schedule_preset != NotificationSchedulePreset.CUSTOM:
            self.custom_schedules = []
        return self


class NotificationPreferencesUpdate(BaseModel):
    timezone: str = "Europe/London"
    lines: list[NotificationLinePreferenceUpdate] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Invalid timezone") from error
        return value

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


class NotificationLinePreferenceRead(NotificationLinePreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)


class NotificationPreferencesRead(NotificationPreferencesUpdate):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    lines: list[NotificationLinePreferenceRead]
    created_at: datetime
    updated_at: datetime


class NotificationTestPushRead(BaseModel):
    device_id: str
    status: str
    provider_message_id: str | None = None
    failure_reason: str | None = None
