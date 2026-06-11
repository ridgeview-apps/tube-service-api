from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.line_status.cache import daily_history_cache
from app.line_status.repository import get_line_history
from app.line_status.schemas import DailyHistoryRead
from app.line_status.time import LONDON, london_day_bounds_utc, today_in_london


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

    settings = get_settings()
    ttl_seconds = (
        settings.history_cache_today_ttl_seconds
        if day == today_in_london()
        else settings.history_cache_past_ttl_seconds
    )
    daily_history_cache.set(
        line_id=normalized_line_id,
        day=day,
        value=history,
        ttl_seconds=ttl_seconds,
    )
    return history
