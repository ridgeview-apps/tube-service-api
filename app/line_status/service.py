from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.lines import SUPPORTED_LINE_IDS
from app.line_status.models import LineStatusSnapshot
from app.line_status.repository import get_disruption_summary, get_line_history
from app.line_status.schemas import (
    DailyTimelineRead,
    LineDisruptionSummaryRead,
    LineStatusRead,
    LineStatusSnapshotRead,
)
from app.line_status.severity import TIMELINE_SEVERITIES
from app.line_status.time import LONDON, london_day_bounds_utc, today_in_london


def _daily_cache_ttl_seconds(day: date) -> int:
    settings = get_settings()
    return (
        settings.history_cache_today_ttl_seconds
        if day == today_in_london()
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
                LineStatusRead.model_validate(status)
                for status in snapshot.statuses
                if status.status_severity in TIMELINE_SEVERITIES
            ),
            key=lambda status: (
                status.status_severity,
                status.status_description,
                status.reason or "",
                status.disruption_category or "",
                status.additional_info or "",
            ),
        )
        if not statuses or statuses == previous_statuses:
            continue

        timeline.append(
            LineStatusSnapshotRead(
                line_id=snapshot.line_id,
                line_name=snapshot.line_name,
                mode_name=snapshot.mode_name,
                observed_at=snapshot.observed_at,
                statuses=statuses,
            )
        )
        previous_statuses = statuses

    timeline.reverse()
    return timeline


async def get_daily_timeline(
    session: AsyncSession,
    line_id: str,
    day: date,
) -> DailyTimelineRead:
    normalized_line_id = line_id.lower()
    cached_timeline = daily_timeline_cache.get(
        line_id=normalized_line_id,
        day=day,
    )
    if cached_timeline is not None:
        return cached_timeline

    start, end = london_day_bounds_utc(day)

    snapshots = await get_line_history(
        session=session,
        line_id=normalized_line_id,
        start=start,
        end=end,
    )
    timeline = DailyTimelineRead(
        line_id=normalized_line_id,
        date=day,
        timezone=str(LONDON),
        snapshots=_timeline_snapshots(snapshots),
    )

    daily_timeline_cache.set(
        line_id=normalized_line_id,
        day=day,
        value=timeline,
        ttl_seconds=_daily_cache_ttl_seconds(day),
    )
    return timeline


async def get_daily_disruption_summary(
    session: AsyncSession,
    day: date,
) -> list[LineDisruptionSummaryRead]:
    cached_summary = daily_disruption_summary_cache.get(day=day)
    if cached_summary is not None:
        return cached_summary

    start, end = london_day_bounds_utc(day)
    disruption_flags = await get_disruption_summary(
        session=session,
        start=start,
        end=end,
    )
    summary = [
        LineDisruptionSummaryRead(
            line_id=line_id,
            disrupted=disruption_flags.get(line_id, False),
        )
        for line_id in sorted(SUPPORTED_LINE_IDS)
    ]
    daily_disruption_summary_cache.set(
        day=day,
        value=summary,
        ttl_seconds=_daily_cache_ttl_seconds(day),
    )
    return summary
