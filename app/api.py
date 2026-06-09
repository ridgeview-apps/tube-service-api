from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.repositories import get_line_snapshots
from app.schemas import DailyHistoryResponse, HealthResponse

router = APIRouter()
LONDON = ZoneInfo("Europe/London")


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/v1/line-status/history",
    response_model=DailyHistoryResponse,
    tags=["line status"],
)
async def daily_line_history(
    line_id: Annotated[str, Query(min_length=1, examples=["victoria"])],
    day: Annotated[date, Query(alias="date")],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DailyHistoryResponse:
    local_start = datetime.combine(day, time.min, tzinfo=LONDON)
    local_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LONDON)

    snapshots = await get_line_snapshots(
        session=session,
        line_id=line_id.lower(),
        start=local_start.astimezone(UTC),
        end=local_end.astimezone(UTC),
    )
    return DailyHistoryResponse(
        line_id=line_id.lower(),
        date=day,
        timezone=str(LONDON),
        snapshots=snapshots,
    )
