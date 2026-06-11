from datetime import date
from unittest.mock import AsyncMock

from app.line_status import service
from app.line_status.cache import daily_history_cache


async def test_daily_history_is_cached_by_line_and_date(monkeypatch) -> None:
    get_line_history = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "get_line_history", get_line_history)
    daily_history_cache.clear()

    requested_day = date(2026, 6, 9)
    session = AsyncMock()

    first_result = await service.get_daily_history(
        session=session,
        line_id="Victoria",
        day=requested_day,
    )
    second_result = await service.get_daily_history(
        session=session,
        line_id="victoria",
        day=requested_day,
    )

    assert first_result == second_result
    assert get_line_history.await_count == 1

    daily_history_cache.clear()
