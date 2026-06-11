from datetime import date
from unittest.mock import AsyncMock

from app.line_status import service
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache


async def test_daily_timeline_is_cached_by_line_and_date(monkeypatch) -> None:
    get_line_history = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "get_line_history", get_line_history)
    daily_timeline_cache.clear()

    requested_day = date(2026, 6, 9)
    session = AsyncMock()

    first_result = await service.get_daily_timeline(
        session=session,
        line_id="Victoria",
        day=requested_day,
    )
    second_result = await service.get_daily_timeline(
        session=session,
        line_id="victoria",
        day=requested_day,
    )

    assert first_result == second_result
    assert get_line_history.await_count == 1

    daily_timeline_cache.clear()


async def test_daily_disruption_summary_is_cached_by_date(monkeypatch) -> None:
    get_disruption_summary = AsyncMock(return_value={"circle": True, "northern": False})
    monkeypatch.setattr(service, "get_disruption_summary", get_disruption_summary)
    daily_disruption_summary_cache.clear()

    requested_day = date(2026, 6, 9)
    session = AsyncMock()

    first_result = await service.get_daily_disruption_summary(
        session=session,
        day=requested_day,
    )
    second_result = await service.get_daily_disruption_summary(
        session=session,
        day=requested_day,
    )

    assert first_result == second_result
    assert get_disruption_summary.await_count == 1

    daily_disruption_summary_cache.clear()
