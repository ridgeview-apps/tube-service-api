from datetime import UTC, datetime

from app.line_status.models import LineStatus, LineStatusSnapshot
from app.notifications.events import (
    NotificationEventType,
    active_disruption_candidate,
    detect_notification_candidate,
)


def snapshot(
    statuses: list[LineStatus],
    *,
    observed_at: datetime = datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
) -> LineStatusSnapshot:
    return LineStatusSnapshot(
        line_id="victoria",
        observed_at=observed_at,
        statuses=statuses,
    )


def status(
    severity: int,
    description: str,
    *,
    reason: str | None = None,
) -> LineStatus:
    return LineStatus(
        status_severity=severity,
        status_description=description,
        reason=reason,
    )


def test_baseline_snapshot_does_not_emit_notification_candidate() -> None:
    candidate = detect_notification_candidate(
        previous_snapshot=None,
        current_snapshot=snapshot([status(9, "Minor Delays")]),
    )

    assert candidate is None


def test_active_disruption_snapshot_emits_current_disruption_candidate() -> None:
    candidate = active_disruption_candidate(
        snapshot=snapshot([status(9, "Minor Delays", reason="Signal failure")])
    )

    assert candidate is not None
    assert candidate.line_id == "victoria"
    assert candidate.event_type == NotificationEventType.DISRUPTION_STARTED
    assert candidate.severity == 9
    assert candidate.status_description == "Minor Delays"
    assert candidate.reason == "Signal failure"


def test_good_service_to_disruption_emits_disruption_started() -> None:
    candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(10, "Good Service")]),
        current_snapshot=snapshot(
            [status(9, "Minor Delays", reason="Signal failure")],
            observed_at=datetime(2026, 6, 16, 8, 5, tzinfo=UTC),
        ),
    )

    assert candidate is not None
    assert candidate.line_id == "victoria"
    assert candidate.event_type == NotificationEventType.DISRUPTION_STARTED
    assert candidate.observed_at == datetime(2026, 6, 16, 8, 5, tzinfo=UTC)
    assert candidate.severity == 9
    assert candidate.status_description == "Minor Delays"
    assert candidate.reason == "Signal failure"
    assert len(candidate.dedupe_key) == 64


def test_disruption_worsening_emits_disruption_changed() -> None:
    candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(9, "Minor Delays")]),
        current_snapshot=snapshot([status(6, "Severe Delays")]),
    )

    assert candidate is not None
    assert candidate.event_type == NotificationEventType.DISRUPTION_CHANGED
    assert candidate.severity == 6
    assert candidate.status_description == "Severe Delays"


def test_disruption_with_same_or_better_severity_does_not_emit_candidate() -> None:
    same_severity_candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(9, "Minor Delays", reason="Signal failure")]),
        current_snapshot=snapshot([status(9, "Minor Delays", reason="Earlier fault")]),
    )
    improved_candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(6, "Severe Delays")]),
        current_snapshot=snapshot([status(9, "Minor Delays")]),
    )

    assert same_severity_candidate is None
    assert improved_candidate is None


def test_disruption_to_good_service_emits_service_resumed() -> None:
    candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(6, "Severe Delays")]),
        current_snapshot=snapshot([status(10, "Good Service")]),
    )

    assert candidate is not None
    assert candidate.event_type == NotificationEventType.SERVICE_RESUMED
    assert candidate.severity == 10
    assert candidate.status_description == "Good Service"


def test_planned_closure_is_not_treated_as_notification_disruption() -> None:
    candidate = detect_notification_candidate(
        previous_snapshot=snapshot([status(10, "Good Service")]),
        current_snapshot=snapshot([status(4, "Planned Closure")]),
    )

    assert candidate is None


def test_dedupe_key_is_stable_for_the_same_candidate() -> None:
    previous_snapshot = snapshot([status(10, "Good Service")])
    current_snapshot = snapshot(
        [status(6, "Severe Delays", reason="Signal failure")],
        observed_at=datetime(2026, 6, 16, 8, 5, tzinfo=UTC),
    )

    first_candidate = detect_notification_candidate(
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    )
    second_candidate = detect_notification_candidate(
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    )

    assert first_candidate is not None
    assert second_candidate is not None
    assert first_candidate.dedupe_key == second_candidate.dedupe_key


def test_dedupe_key_is_stable_after_timezone_is_dropped() -> None:
    aware_candidate = active_disruption_candidate(
        snapshot=snapshot(
            [status(6, "Severe Delays", reason="Signal failure")],
            observed_at=datetime(2026, 6, 16, 8, 5, tzinfo=UTC),
        )
    )
    naive_candidate = active_disruption_candidate(
        snapshot=snapshot(
            [status(6, "Severe Delays", reason="Signal failure")],
            observed_at=datetime(2026, 6, 16, 8, 5),
        )
    )

    assert aware_candidate is not None
    assert naive_candidate is not None
    assert aware_candidate.dedupe_key == naive_candidate.dedupe_key
