from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.line_status.severity import TflRailStatusSeverity
from app.notifications.events import NotificationCandidate, NotificationEventType
from app.notifications.models import NotificationDevice, NotificationPreferences
from app.notifications.schemas import (
    NotificationSchedulePreset,
    NotificationScheduleWindow,
    NotificationSeverityThreshold,
    PushPlatform,
)


@dataclass(frozen=True)
class NotificationDeliveryTarget:
    device_id: str
    platform: PushPlatform
    push_token: str


def matching_delivery_targets(
    *,
    candidate: NotificationCandidate,
    devices: list[NotificationDevice],
    now: datetime | None = None,
) -> list[NotificationDeliveryTarget]:
    return [
        NotificationDeliveryTarget(
            device_id=device.device_id,
            platform=PushPlatform(device.platform),
            push_token=device.push_token,
        )
        for device in devices
        if device_matches_candidate(candidate=candidate, device=device, now=now)
    ]


def device_matches_candidate(
    *,
    candidate: NotificationCandidate,
    device: NotificationDevice,
    now: datetime | None = None,
) -> bool:
    preferences = device.preferences
    if not device.enabled or preferences is None or not preferences.enabled:
        return False
    if candidate.line_id not in preferences.line_ids:
        return False
    if candidate.event_type == NotificationEventType.SERVICE_RESUMED:
        if not preferences.notify_recoveries:
            return False
    elif not _severity_matches_threshold(candidate.severity, preferences.severity_threshold):
        return False

    checked_at = now or candidate.observed_at
    return _within_schedule(preferences=preferences, checked_at=checked_at)


def _severity_matches_threshold(severity: int, threshold: str) -> bool:
    match NotificationSeverityThreshold(threshold):
        case NotificationSeverityThreshold.MINOR_DELAYS:
            return severity <= TflRailStatusSeverity.MINOR_DELAYS
        case NotificationSeverityThreshold.SEVERE_DELAYS:
            return severity <= TflRailStatusSeverity.SEVERE_DELAYS
        case NotificationSeverityThreshold.SUSPENDED:
            return severity in {
                TflRailStatusSeverity.CLOSED,
                TflRailStatusSeverity.SUSPENDED,
                TflRailStatusSeverity.PART_SUSPENDED,
            }


def _within_schedule(
    *,
    preferences: NotificationPreferences,
    checked_at: datetime,
) -> bool:
    try:
        local_time = checked_at.astimezone(ZoneInfo(preferences.timezone))
    except ZoneInfoNotFoundError:
        return False

    match NotificationSchedulePreset(preferences.schedule_preset):
        case NotificationSchedulePreset.ANYTIME:
            return True
        case NotificationSchedulePreset.WEEKDAY_PEAK:
            windows = _weekday_peak_windows()
        case NotificationSchedulePreset.WEEKDAY_MORNING_PEAK:
            windows = [
                _window(
                    start_time=time(7, 0),
                    end_time=time(9, 30),
                )
            ]
        case NotificationSchedulePreset.WEEKDAY_EVENING_PEAK:
            windows = [
                _window(
                    start_time=time(16, 30),
                    end_time=time(19, 0),
                )
            ]
        case NotificationSchedulePreset.CUSTOM:
            windows = [
                NotificationScheduleWindow.model_validate(schedule)
                for schedule in preferences.custom_schedules
            ]

    return any(_window_contains(window=window, checked_at=local_time) for window in windows)


def _weekday_peak_windows() -> list[NotificationScheduleWindow]:
    return [
        _window(
            start_time=time(7, 0),
            end_time=time(9, 30),
        ),
        _window(
            start_time=time(16, 30),
            end_time=time(19, 0),
        ),
    ]


def _window(
    *,
    start_time: time,
    end_time: time,
) -> NotificationScheduleWindow:
    return NotificationScheduleWindow(
        days=["mon", "tue", "wed", "thu", "fri"],
        start_time=start_time,
        end_time=end_time,
    )


def _window_contains(
    *,
    window: NotificationScheduleWindow,
    checked_at: datetime,
) -> bool:
    weekday = checked_at.strftime("%a").lower()
    return weekday in window.days and window.start_time <= checked_at.time() < window.end_time
