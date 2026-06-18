from datetime import UTC, date, datetime

from app.line_status.cache import DailyDisruptionSummaryCache, DailyTimelineCache
from app.line_status.schemas import (
    DailyDisruptionSummaryRead,
    DailyTimelineRead,
    LineStatusRead,
    LineStatusSnapshotRead,
    LineStatusTransition,
)
from app.line_status.time import operational_day_bounds_london


class FakeClock:
    def __init__(self) -> None:
        self.current_time = 0.0

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def _timeline(*, line_id: str, operational_date: date) -> DailyTimelineRead:
    starts_at, ends_at = operational_day_bounds_london(operational_date)
    return DailyTimelineRead(
        line_id=line_id,
        operational_date=operational_date,
        timezone="Europe/London",
        starts_at=starts_at,
        ends_at=ends_at,
        snapshots=[],
    )


def _disruption_snapshot(*, line_id: str, observed_at: datetime) -> LineStatusSnapshotRead:
    return LineStatusSnapshotRead(
        line_id=line_id,
        observed_at=observed_at,
        transition=LineStatusTransition.DISRUPTION_STARTED,
        statuses=[
            LineStatusRead(
                status_severity=9,
                status_severity_description="Minor Delays",
                reason="Signal failure",
                disruption=None,
            )
        ],
    )


def test_stored_timeline_can_be_retrieved() -> None:
    cache = DailyTimelineCache()
    operational_date = date(2026, 6, 11)
    timeline = _timeline(line_id="victoria", operational_date=operational_date)

    cache.set(
        line_id="victoria",
        operational_date=operational_date,
        value=timeline,
        ttl_seconds=60,
    )

    assert cache.get(line_id="victoria", operational_date=operational_date) == timeline


def test_line_and_operational_date_are_separate_cache_keys() -> None:
    cache = DailyTimelineCache()
    first_operational_date = date(2026, 6, 10)
    second_operational_date = date(2026, 6, 11)
    victoria_timeline = _timeline(line_id="victoria", operational_date=first_operational_date)
    central_timeline = _timeline(line_id="central", operational_date=first_operational_date)

    cache.set(
        line_id="victoria",
        operational_date=first_operational_date,
        value=victoria_timeline,
        ttl_seconds=60,
    )
    cache.set(
        line_id="central",
        operational_date=first_operational_date,
        value=central_timeline,
        ttl_seconds=60,
    )

    assert (
        cache.get(line_id="victoria", operational_date=first_operational_date) == victoria_timeline
    )
    assert cache.get(line_id="central", operational_date=first_operational_date) == central_timeline
    assert cache.get(line_id="victoria", operational_date=second_operational_date) is None


def test_expired_timeline_is_removed() -> None:
    clock = FakeClock()
    cache = DailyTimelineCache(clock=clock)
    operational_date = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        operational_date=operational_date,
        value=_timeline(line_id="victoria", operational_date=operational_date),
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(line_id="victoria", operational_date=operational_date) is None


def test_zero_ttl_does_not_store_timeline() -> None:
    cache = DailyTimelineCache()
    operational_date = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        operational_date=operational_date,
        value=_timeline(line_id="victoria", operational_date=operational_date),
        ttl_seconds=0,
    )

    assert cache.get(line_id="victoria", operational_date=operational_date) is None


def test_clear_removes_all_timelines() -> None:
    cache = DailyTimelineCache()
    operational_date = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        operational_date=operational_date,
        value=_timeline(line_id="victoria", operational_date=operational_date),
        ttl_seconds=60,
    )
    cache.clear()

    assert cache.get(line_id="victoria", operational_date=operational_date) is None


def test_oldest_timeline_is_evicted_when_cache_is_full() -> None:
    cache = DailyTimelineCache(max_entries=2)
    operational_date = date(2026, 6, 11)

    for line_id in ("victoria", "central", "jubilee"):
        cache.set(
            line_id=line_id,
            operational_date=operational_date,
            value=_timeline(line_id=line_id, operational_date=operational_date),
            ttl_seconds=60,
        )

    assert cache.get(line_id="victoria", operational_date=operational_date) is None
    assert cache.get(line_id="central", operational_date=operational_date) is not None
    assert cache.get(line_id="jubilee", operational_date=operational_date) is not None


def test_disruption_summary_is_cached_by_operational_date() -> None:
    cache = DailyDisruptionSummaryCache()
    first_operational_date = date(2026, 6, 10)
    second_operational_date = date(2026, 6, 11)
    starts_at, ends_at = operational_day_bounds_london(first_operational_date)
    summary = DailyDisruptionSummaryRead(
        operational_date=first_operational_date,
        timezone="Europe/London",
        starts_at=starts_at,
        ends_at=ends_at,
        lines={
            "circle": [
                _disruption_snapshot(
                    line_id="circle",
                    observed_at=datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
                )
            ],
            "northern": [],
        },
    )

    cache.set(operational_date=first_operational_date, value=summary, ttl_seconds=60)

    assert cache.get(operational_date=first_operational_date) == summary
    assert cache.get(operational_date=second_operational_date) is None


def test_expired_disruption_summary_is_removed() -> None:
    clock = FakeClock()
    cache = DailyDisruptionSummaryCache(clock=clock)
    operational_date = date(2026, 6, 11)
    starts_at, ends_at = operational_day_bounds_london(operational_date)

    cache.set(
        operational_date=operational_date,
        value=DailyDisruptionSummaryRead(
            operational_date=operational_date,
            timezone="Europe/London",
            starts_at=starts_at,
            ends_at=ends_at,
            lines={
                "circle": [
                    _disruption_snapshot(
                        line_id="circle",
                        observed_at=datetime(2026, 6, 11, 8, 0, tzinfo=UTC),
                    )
                ]
            },
        ),
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(operational_date=operational_date) is None
