from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.line_status.repository import get_line_snapshots
from app.line_status.schemas import DailyHistoryResponse

LONDON = ZoneInfo("Europe/London")


async def get_daily_history(
    session: AsyncSession,
    line_id: str,
    day: date,
) -> DailyHistoryResponse:
    normalized_line_id = line_id.lower()
    local_start = datetime.combine(day, time.min, tzinfo=LONDON)
    local_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LONDON)

    snapshots = await get_line_snapshots(
        session=session,
        line_id=normalized_line_id,
        start=local_start.astimezone(UTC),
        end=local_end.astimezone(UTC),
    )
    return DailyHistoryResponse(
        line_id=normalized_line_id,
        date=day,
        timezone=str(LONDON),
        snapshots=snapshots,
    )
