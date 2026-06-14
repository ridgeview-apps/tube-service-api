from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from app.line_status import service
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.lines import SUPPORTED_LINE_IDS


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
    disruption_at = datetime(2026, 6, 9, 8, 0, tzinfo=UTC)
    get_disruption_summary = AsyncMock(
        return_value={"circle": (2, disruption_at), "northern": (0, None)}
    )
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
    assert first_result.date == requested_day
    assert first_result.timezone == "Europe/London"
    assert set(first_result.lines) == SUPPORTED_LINE_IDS
    assert first_result.lines["circle"].disrupted
    assert first_result.lines["circle"].disruption_count == 2
    assert first_result.lines["circle"].latest_disruption_at == disruption_at
    assert not first_result.lines["northern"].disrupted
    assert first_result.lines["northern"].disruption_count == 0
    assert first_result.lines["northern"].latest_disruption_at is None

    daily_disruption_summary_cache.clear()
