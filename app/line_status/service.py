from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.lines import SUPPORTED_LINE_IDS
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.repository import get_disruption_summary, get_line_history
from app.line_status.schemas import (
    DailyDisruptionSummaryRead,
    DailyTimelineRead,
    DisruptionRead,
    LineDisruptionSummaryRead,
    LineStatusRead,
    LineStatusSnapshotRead,
    LineStatusTransition,
)
from app.line_status.severity import (
    DISRUPTION_SEVERITIES,
    TIMELINE_SEVERITIES,
    TflRailStatusSeverity,
)
from app.line_status.time import (
    LONDON,
    current_operational_day,
    operational_day_bounds_london,
    operational_day_bounds_utc,
)


def _daily_cache_ttl_seconds(operational_date: date) -> int:
    settings = get_settings()
    return (
        settings.history_cache_today_ttl_seconds
        if operational_date == current_operational_day()
        else settings.history_cache_past_ttl_seconds
    )


def _timeline_snapshots(
    snapshots: list[LineStatusSnapshot],
) -> list[LineStatusSnapshotRead]:
    timeline: list[LineStatusSnapshotRead] = []
    previous_statuses: list[LineStatusRead] | None = None

    for snapshot in reversed(snapshots):
        statuses = sorted(
            (
                _line_status_read(status)
                for status in snapshot.statuses
                if status.status_severity in TIMELINE_SEVERITIES
            ),
            key=lambda status: (
                status.status_severity,
                status.status_severity_description,
                status.reason or "",
                (status.disruption.category or "") if status.disruption else "",
                (status.disruption.additional_info or "") if status.disruption else "",
            ),
        )
        if not statuses or statuses == previous_statuses:
            continue

        transition = _status_transition(
            previous_statuses=previous_statuses,
            current_statuses=statuses,
        )
        timeline.append(
            LineStatusSnapshotRead(
                line_id=snapshot.line_id,
                observed_at=snapshot.observed_at,
                transition=transition,
                statuses=statuses,
            )
        )
        previous_statuses = statuses

    timeline.reverse()
    return timeline


def _status_transition(
    *,
    previous_statuses: list[LineStatusRead] | None,
    current_statuses: list[LineStatusRead],
) -> LineStatusTransition:
    if previous_statuses is None:
        return LineStatusTransition.BASELINE

    previous_disrupted = _statuses_are_disrupted(previous_statuses)
    current_disrupted = _statuses_are_disrupted(current_statuses)
    if current_disrupted:
        return (
            LineStatusTransition.DISRUPTION_CHANGED
            if previous_disrupted
            else LineStatusTransition.DISRUPTION_STARTED
        )

    current_has_good_service = any(
        status.status_severity == TflRailStatusSeverity.GOOD_SERVICE for status in current_statuses
    )
    if previous_disrupted and current_has_good_service:
        return LineStatusTransition.SERVICE_RESUMED

    return LineStatusTransition.STATUS_CHANGED


def _statuses_are_disrupted(statuses: list[LineStatusRead]) -> bool:
    return any(status.status_severity in DISRUPTION_SEVERITIES for status in statuses)


def _line_status_read(status: LineStatus) -> LineStatusRead:
    disruption_category = status.disruption_category
    additional_info = status.additional_info
    disruption = (
        DisruptionRead(
            category=disruption_category,
            additional_info=additional_info,
        )
        if disruption_category is not None or additional_info is not None
        else None
    )
    return LineStatusRead(
        status_severity=status.status_severity,
        status_severity_description=status.status_description,
        reason=status.reason,
        disruption=disruption,
    )


async def get_daily_timeline(
    session: AsyncSession,
    line_id: str,
    operational_date: date,
) -> DailyTimelineRead:
    normalized_line_id = line_id.lower()
    cached_timeline = daily_timeline_cache.get(
        line_id=normalized_line_id,
        operational_date=operational_date,
    )
    if cached_timeline is not None:
        return cached_timeline

    start, end = operational_day_bounds_utc(operational_date)
    local_start, local_end = operational_day_bounds_london(operational_date)

    snapshots = await get_line_history(
        session=session,
        line_id=normalized_line_id,
        start=start,
        end=end,
    )
    timeline = DailyTimelineRead(
        line_id=normalized_line_id,
        operational_date=operational_date,
        timezone=str(LONDON),
        starts_at=local_start,
        ends_at=local_end,
        snapshots=_timeline_snapshots(snapshots),
    )

    daily_timeline_cache.set(
        line_id=normalized_line_id,
        operational_date=operational_date,
        value=timeline,
        ttl_seconds=_daily_cache_ttl_seconds(operational_date),
    )
    return timeline


async def get_daily_disruption_summary(
    session: AsyncSession,
    operational_date: date,
) -> DailyDisruptionSummaryRead:
    cached_summary = daily_disruption_summary_cache.get(operational_date=operational_date)
    if cached_summary is not None:
        return cached_summary

    start, end = operational_day_bounds_utc(operational_date)
    local_start, local_end = operational_day_bounds_london(operational_date)
    disruptions = await get_disruption_summary(
        session=session,
        start=start,
        end=end,
    )
    summary = DailyDisruptionSummaryRead(
        operational_date=operational_date,
        timezone=str(LONDON),
        starts_at=local_start,
        ends_at=local_end,
        lines={
            line_id: LineDisruptionSummaryRead(
                disrupted=disruptions.get(line_id, (0, None))[0] > 0,
                disruption_count=disruptions.get(line_id, (0, None))[0],
                latest_disruption_at=disruptions.get(line_id, (0, None))[1],
            )
            for line_id in sorted(SUPPORTED_LINE_IDS)
        },
    )
    daily_disruption_summary_cache.set(
        operational_date=operational_date,
        value=summary,
        ttl_seconds=_daily_cache_ttl_seconds(operational_date),
    )
    return summary
