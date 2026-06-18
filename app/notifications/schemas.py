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
    WEEKDAY_MORNING_PEAK = "weekday_morning_peak"
    WEEKDAY_EVENING_PEAK = "weekday_evening_peak"
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


class NotificationPreferencesUpdate(BaseModel):
    enabled: bool = True
    line_ids: list[str] = Field(default_factory=list)
    severity_threshold: NotificationSeverityThreshold = NotificationSeverityThreshold.MINOR_DELAYS
    notify_recoveries: bool = True
    timezone: str = "Europe/London"
    schedule_preset: NotificationSchedulePreset = NotificationSchedulePreset.WEEKDAY_PEAK
    custom_schedules: list[NotificationScheduleWindow] = Field(default_factory=list)

    @field_validator("line_ids", mode="before")
    @classmethod
    def normalize_line_ids(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [line_id.lower() if isinstance(line_id, str) else line_id for line_id in value]

    @field_validator("line_ids")
    @classmethod
    def validate_line_ids(cls, value: list[str]) -> list[str]:
        unique_line_ids = list(dict.fromkeys(value))
        unsupported_line_ids = sorted(set(unique_line_ids) - SUPPORTED_LINE_IDS)
        if unsupported_line_ids:
            raise ValueError(f"Unsupported line IDs: {', '.join(unsupported_line_ids)}")
        return unique_line_ids

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Invalid timezone") from error
        return value

    @model_validator(mode="after")
    def require_custom_schedules_for_custom_preset(self) -> "NotificationPreferencesUpdate":
        if self.schedule_preset == NotificationSchedulePreset.CUSTOM and not self.custom_schedules:
            raise ValueError("custom_schedules is required for the custom preset")
        if self.schedule_preset != NotificationSchedulePreset.CUSTOM:
            self.custom_schedules = []
        return self


class NotificationPreferencesRead(NotificationPreferencesUpdate):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    created_at: datetime
    updated_at: datetime


class NotificationTestPushRead(BaseModel):
    device_id: str
    status: str
    provider_message_id: str | None = None
    failure_reason: str | None = None
