from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LineStatusSnapshot


async def get_line_snapshots(
    session: AsyncSession,
    line_id: str,
    start: datetime,
    end: datetime,
) -> list[LineStatusSnapshot]:
    statement = (
        select(LineStatusSnapshot)
        .where(
            LineStatusSnapshot.line_id == line_id,
            LineStatusSnapshot.observed_at >= start,
            LineStatusSnapshot.observed_at < end,
        )
        .order_by(LineStatusSnapshot.observed_at)
    )
    return list((await session.scalars(statement)).all())
