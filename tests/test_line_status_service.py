from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

from app.line_status import service
from app.line_status.cache import daily_disruption_summary_cache, daily_timeline_cache
from app.line_status.lines import SUPPORTED_LINE_IDS
from app.line_status.models import LineStatus, LineStatusSnapshot
from app.line_status.schemas import LineStatusRead, LineStatusTransition


def status(severity: int, description: str) -> LineStatusRead:
    return LineStatusRead(
        status_severity=severity,
        status_severity_description=description,
        reason=None,
        disruption=None,
    )


def test_status_transition_classifies_non_disruption_changes() -> None:
    good_service = [status(10, "Good Service")]
    planned_closure = [status(4, "Planned Closure")]

    assert (
        service._status_transition(
            previous_statuses=good_service,
            current_statuses=planned_closure,
        )
        == LineStatusTransition.STATUS_CHANGED
    )


def test_good_service_alongside_disruption_does_not_resume_service() -> None:
    disrupted = [status(6, "Severe Delays")]
    mixed_statuses = [
        status(6, "Severe Delays"),
        status(10, "Good Service"),
    ]

    assert (
        service._status_transition(
            previous_statuses=disrupted,
            current_statuses=mixed_statuses,
        )
        == LineStatusTransition.DISRUPTION_CHANGED
    )


async def test_daily_timeline_is_cached_by_line_and_operational_date(monkeypatch) -> None:
    get_line_history = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "get_line_history", get_line_history)
    daily_timeline_cache.clear()

    requested_operational_date = date(2026, 6, 9)
    session = AsyncMock()

    first_result = await service.get_daily_timeline(
        session=session,
        line_id="Victoria",
        operational_date=requested_operational_date,
    )
    second_result = await service.get_daily_timeline(
        session=session,
        line_id="victoria",
        operational_date=requested_operational_date,
    )

    assert first_result == second_result
    assert get_line_history.await_count == 1

    daily_timeline_cache.clear()


async def test_daily_disruption_summary_is_cached_by_operational_date(monkeypatch) -> None:
    get_line_histories = AsyncMock(
        return_value={
            "circle": [
                LineStatusSnapshot(
                    line_id="circle",
                    observed_at=datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=9,
                            status_description="Minor Delays",
                            reason="Signal failure",
                        )
                    ],
                ),
                LineStatusSnapshot(
                    line_id="circle",
                    observed_at=datetime(2026, 6, 9, 8, 0, tzinfo=UTC),
                    statuses=[
                        LineStatus(
                            status_severity=10,
                            status_description="Good Service",
                            reason=None,
                        )
                    ],
                ),
            ],
            "northern": [],
        }
    )
    monkeypatch.setattr(service, "get_line_histories", get_line_histories)
    daily_disruption_summary_cache.clear()

    requested_operational_date = date(2026, 6, 9)
    session = AsyncMock()

    first_result = await service.get_daily_disruption_summary(
        session=session,
        operational_date=requested_operational_date,
    )
    second_result = await service.get_daily_disruption_summary(
        session=session,
        operational_date=requested_operational_date,
    )

    assert first_result == second_result
    assert get_line_histories.await_count == 1
    assert first_result.operational_date == requested_operational_date
    assert first_result.timezone == "Europe/London"
    assert set(first_result.lines) == SUPPORTED_LINE_IDS
    assert len(first_result.lines["circle"]) == 1
    assert first_result.lines["circle"][0].observed_at == datetime(2026, 6, 9, 9, 0, tzinfo=UTC)
    assert first_result.lines["circle"][0].transition == LineStatusTransition.DISRUPTION_STARTED
    assert first_result.lines["northern"] == []

    daily_disruption_summary_cache.clear()
