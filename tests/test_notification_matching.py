from datetime import UTC, datetime

from app.notifications.events import NotificationCandidate, NotificationEventType
from app.notifications.matching import (
    NotificationDeliveryTarget,
    device_matches_candidate,
    matching_delivery_targets,
)
from app.notifications.models import (
    NotificationDevice,
    NotificationLinePreference,
    NotificationPreferences,
)


def candidate(
    *,
    line_id: str = "victoria",
    event_type: NotificationEventType = NotificationEventType.DISRUPTION_STARTED,
    severity: int = 9,
    observed_at: datetime = datetime(2026, 6, 16, 7, 30, tzinfo=UTC),
) -> NotificationCandidate:
    return NotificationCandidate(
        line_id=line_id,
        event_type=event_type,
        observed_at=observed_at,
        severity=severity,
        status_description="Minor Delays",
        reason=None,
        dedupe_key="candidate-key",
    )


def device(
    *,
    device_id: str = "install-123",
    enabled: bool = True,
    line_enabled: bool = True,
    line_ids: list[str] | None = None,
    severity_threshold: str = "minor_delays",
    notify_recoveries: bool = True,
    timezone: str = "Europe/London",
    schedule_preset: str = "anytime",
    custom_schedules: list[dict[str, object]] | None = None,
) -> NotificationDevice:
    notification_device = NotificationDevice(
        device_id=device_id,
        platform="ios",
        push_token=f"{device_id}-token",
        enabled=enabled,
        app_version=None,
        created_at=datetime(2026, 6, 16, 6, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 16, 6, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 6, 16, 6, 0, tzinfo=UTC),
    )
    notification_device.preferences = NotificationPreferences(
        device_id=device_id,
        timezone=timezone,
        created_at=datetime(2026, 6, 16, 6, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 16, 6, 0, tzinfo=UTC),
        lines=[
            NotificationLinePreference(
                device_id=device_id,
                line_id=line_id,
                enabled=line_enabled,
                severity_threshold=severity_threshold,
                notify_recoveries=notify_recoveries,
                schedule_preset=schedule_preset,
                custom_schedules=custom_schedules or [],
            )
            for line_id in (line_ids or ["victoria"])
        ],
    )
    return notification_device


def test_enabled_device_with_matching_line_threshold_and_schedule_matches() -> None:
    assert device_matches_candidate(
        candidate=candidate(severity=9),
        device=device(),
    )


def test_disabled_device_or_line_preference_does_not_match() -> None:
    assert not device_matches_candidate(
        candidate=candidate(),
        device=device(enabled=False),
    )
    assert not device_matches_candidate(
        candidate=candidate(),
        device=device(line_enabled=False),
    )


def test_missing_preferences_do_not_match() -> None:
    notification_device = device()
    notification_device.preferences = None

    assert not device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
    )


def test_device_must_subscribe_to_candidate_line() -> None:
    assert not device_matches_candidate(
        candidate=candidate(line_id="central"),
        device=device(line_ids=["victoria"]),
    )


def test_each_line_uses_its_own_notification_settings() -> None:
    notification_device = device(line_ids=["victoria", "central"])
    central_preferences = next(
        line for line in notification_device.preferences.lines if line.line_id == "central"
    )
    central_preferences.severity_threshold = "suspended"

    assert device_matches_candidate(
        candidate=candidate(line_id="victoria", severity=9),
        device=notification_device,
    )
    assert not device_matches_candidate(
        candidate=candidate(line_id="central", severity=9),
        device=notification_device,
    )


def test_severity_threshold_filters_disruption_events() -> None:
    assert device_matches_candidate(
        candidate=candidate(severity=6),
        device=device(severity_threshold="severe_delays"),
    )
    assert not device_matches_candidate(
        candidate=candidate(severity=9),
        device=device(severity_threshold="severe_delays"),
    )
    assert device_matches_candidate(
        candidate=candidate(severity=2),
        device=device(severity_threshold="suspended"),
    )
    assert not device_matches_candidate(
        candidate=candidate(severity=6),
        device=device(severity_threshold="suspended"),
    )


def test_recovery_events_use_recovery_preference_not_severity_threshold() -> None:
    recovery = candidate(
        event_type=NotificationEventType.SERVICE_RESUMED,
        severity=10,
    )

    assert device_matches_candidate(
        candidate=recovery,
        device=device(severity_threshold="suspended", notify_recoveries=True),
    )
    assert not device_matches_candidate(
        candidate=recovery,
        device=device(severity_threshold="minor_delays", notify_recoveries=False),
    )


def test_weekday_peak_schedule_matches_morning_and_evening_windows() -> None:
    notification_device = device(schedule_preset="weekday_peak")

    assert device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
        now=datetime(2026, 6, 16, 6, 30, tzinfo=UTC),
    )
    assert device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
        now=datetime(2026, 6, 16, 16, 0, tzinfo=UTC),
    )
    assert not device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
        now=datetime(2026, 6, 16, 12, 0, tzinfo=UTC),
    )


def test_weekday_peak_schedule_excludes_weekends() -> None:
    assert not device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekday_peak"),
        now=datetime(2026, 6, 20, 8, 0, tzinfo=UTC),
    )


def test_weekday_all_day_matches_only_weekdays() -> None:
    assert device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekday_all_day"),
        now=datetime(2026, 6, 16, 2, 0, tzinfo=UTC),
    )
    assert device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekday_all_day"),
        now=datetime(2026, 6, 16, 22, 0, tzinfo=UTC),
    )
    assert not device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekday_all_day"),
        now=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )


def test_weekends_matches_only_saturday_and_sunday() -> None:
    assert device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekends"),
        now=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )
    assert device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekends"),
        now=datetime(2026, 6, 21, 12, 0, tzinfo=UTC),
    )
    assert not device_matches_candidate(
        candidate=candidate(),
        device=device(schedule_preset="weekends"),
        now=datetime(2026, 6, 22, 12, 0, tzinfo=UTC),
    )


def test_custom_schedule_uses_device_timezone() -> None:
    notification_device = device(
        timezone="Europe/London",
        schedule_preset="custom",
        custom_schedules=[
            {
                "days": ["tue"],
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            }
        ],
    )

    assert device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
        now=datetime(2026, 6, 16, 7, 30, tzinfo=UTC),
    )
    assert not device_matches_candidate(
        candidate=candidate(),
        device=notification_device,
        now=datetime(2026, 6, 16, 9, 30, tzinfo=UTC),
    )


def test_matching_delivery_targets_returns_push_safe_target_data() -> None:
    targets = matching_delivery_targets(
        candidate=candidate(),
        devices=[
            device(device_id="install-1"),
            device(device_id="install-2", line_ids=["central"]),
        ],
    )

    assert targets == [
        NotificationDeliveryTarget(
            device_id="install-1",
            platform="ios",
            push_token="install-1-token",
        )
    ]
