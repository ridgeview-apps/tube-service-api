from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.severity import DISRUPTION_SEVERITIES, TflRailStatusSeverity


class NotificationEventType(StrEnum):
    DISRUPTION_STARTED = "disruption_started"
    DISRUPTION_CHANGED = "disruption_changed"
    SERVICE_RESUMED = "service_resumed"


@dataclass(frozen=True)
class NotificationCandidate:
    line_id: str
    event_type: NotificationEventType
    observed_at: datetime
    severity: int
    status_description: str
    reason: str | None
    dedupe_key: str


def detect_notification_candidate(
    *,
    previous_snapshot: LineStatusSnapshot | None,
    current_snapshot: LineStatusSnapshot,
) -> NotificationCandidate | None:
    if previous_snapshot is None:
        return None

    previous_disruption = _most_severe_disruption(previous_snapshot.statuses)
    current_disruption = _most_severe_disruption(current_snapshot.statuses)

    if current_disruption is not None:
        if previous_disruption is None:
            return _candidate(
                snapshot=current_snapshot,
                event_type=NotificationEventType.DISRUPTION_STARTED,
                status=current_disruption,
            )
        if current_disruption.status_severity < previous_disruption.status_severity:
            return _candidate(
                snapshot=current_snapshot,
                event_type=NotificationEventType.DISRUPTION_CHANGED,
                status=current_disruption,
            )
        return None

    if previous_disruption is not None:
        good_service = _good_service_status(current_snapshot.statuses)
        if good_service is not None:
            return _candidate(
                snapshot=current_snapshot,
                event_type=NotificationEventType.SERVICE_RESUMED,
                status=good_service,
            )

    return None


def _most_severe_disruption(statuses: list[LineStatus]) -> LineStatus | None:
    disruption_statuses = [
        status for status in statuses if status.status_severity in DISRUPTION_SEVERITIES
    ]
    if not disruption_statuses:
        return None
    return min(
        disruption_statuses,
        key=lambda status: (
            status.status_severity,
            status.status_description,
            status.reason or "",
        ),
    )


def _good_service_status(statuses: list[LineStatus]) -> LineStatus | None:
    return next(
        (
            status
            for status in statuses
            if status.status_severity == TflRailStatusSeverity.GOOD_SERVICE
        ),
        None,
    )


def _candidate(
    *,
    snapshot: LineStatusSnapshot,
    event_type: NotificationEventType,
    status: LineStatus,
) -> NotificationCandidate:
    key_parts = [
        snapshot.line_id,
        event_type.value,
        snapshot.observed_at.isoformat(),
        str(status.status_severity),
        status.status_description,
        status.reason or "",
    ]
    return NotificationCandidate(
        line_id=snapshot.line_id,
        event_type=event_type,
        observed_at=snapshot.observed_at,
        severity=status.status_severity,
        status_description=status.status_description,
        reason=status.reason,
        dedupe_key=sha256("|".join(key_parts).encode()).hexdigest(),
    )
