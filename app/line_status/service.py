from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.line_status.cache import daily_disruption_summary_cache, daily_history_cache
from app.line_status.repository import get_disruption_summary, get_line_history
from app.line_status.schemas import DailyHistoryRead, LineDisruptionSummaryRead
from app.line_status.time import LONDON, london_day_bounds_utc, today_in_london


def _daily_cache_ttl_seconds(day: date) -> int:
    settings = get_settings()
    return (
        settings.history_cache_today_ttl_seconds
        if day == today_in_london()
        else settings.history_cache_past_ttl_seconds
    )


async def get_daily_history(
    session: AsyncSession,
    line_id: str,
    day: date,
) -> DailyHistoryRead:
    normalized_line_id = line_id.lower()
    cached_history = daily_history_cache.get(
        line_id=normalized_line_id,
        day=day,
    )
    if cached_history is not None:
        return cached_history

    start, end = london_day_bounds_utc(day)

    snapshots = await get_line_history(
        session=session,
        line_id=normalized_line_id,
        start=start,
        end=end,
    )
    history = DailyHistoryRead(
        line_id=normalized_line_id,
        date=day,
        timezone=str(LONDON),
        snapshots=snapshots,
    )

    daily_history_cache.set(
        line_id=normalized_line_id,
        day=day,
        value=history,
        ttl_seconds=_daily_cache_ttl_seconds(day),
    )
    return history


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
        LineDisruptionSummaryRead(line_id=line_id, disrupted=disrupted)
        for line_id, disrupted in disruption_flags.items()
    ]
    daily_disruption_summary_cache.set(
        day=day,
        value=summary,
        ttl_seconds=_daily_cache_ttl_seconds(day),
    )
    return summary
