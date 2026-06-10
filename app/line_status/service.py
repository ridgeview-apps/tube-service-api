from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.line_status.repository import get_line_history
from app.line_status.schemas import DailyHistoryRead
from app.line_status.time import LONDON, london_day_bounds_utc


async def get_daily_history(
    session: AsyncSession,
    line_id: str,
    day: date,
) -> DailyHistoryRead:
    normalized_line_id = line_id.lower()
    start, end = london_day_bounds_utc(day)

    snapshots = await get_line_history(
        session=session,
        line_id=normalized_line_id,
        start=start,
        end=end,
    )
    return DailyHistoryRead(
        line_id=normalized_line_id,
        date=day,
        timezone=str(LONDON),
        snapshots=snapshots,
    )
