from datetime import UTC, date, datetime

from app.line_status.cache import DailyDisruptionSummaryCache, DailyTimelineCache
from app.line_status.schemas import (
    DailyDisruptionSummaryRead,
    DailyTimelineRead,
    LineDisruptionSummaryRead,
)


class FakeClock:
    def __init__(self) -> None:
        self.current_time = 0.0

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def _timeline(*, line_id: str, day: date) -> DailyTimelineRead:
    return DailyTimelineRead(
        line_id=line_id,
        date=day,
        timezone="Europe/London",
        snapshots=[],
    )


def test_stored_timeline_can_be_retrieved() -> None:
    cache = DailyTimelineCache()
    day = date(2026, 6, 11)
    timeline = _timeline(line_id="victoria", day=day)

    cache.set(
        line_id="victoria",
        day=day,
        value=timeline,
        ttl_seconds=60,
    )

    assert cache.get(line_id="victoria", day=day) == timeline


def test_line_and_date_are_separate_cache_keys() -> None:
    cache = DailyTimelineCache()
    first_day = date(2026, 6, 10)
    second_day = date(2026, 6, 11)
    victoria_timeline = _timeline(line_id="victoria", day=first_day)
    central_timeline = _timeline(line_id="central", day=first_day)

    cache.set(
        line_id="victoria",
        day=first_day,
        value=victoria_timeline,
        ttl_seconds=60,
    )
    cache.set(
        line_id="central",
        day=first_day,
        value=central_timeline,
        ttl_seconds=60,
    )

    assert cache.get(line_id="victoria", day=first_day) == victoria_timeline
    assert cache.get(line_id="central", day=first_day) == central_timeline
    assert cache.get(line_id="victoria", day=second_day) is None


def test_expired_timeline_is_removed() -> None:
    clock = FakeClock()
    cache = DailyTimelineCache(clock=clock)
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_timeline(line_id="victoria", day=day),
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(line_id="victoria", day=day) is None


def test_zero_ttl_does_not_store_timeline() -> None:
    cache = DailyTimelineCache()
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_timeline(line_id="victoria", day=day),
        ttl_seconds=0,
    )

    assert cache.get(line_id="victoria", day=day) is None


def test_clear_removes_all_timelines() -> None:
    cache = DailyTimelineCache()
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_timeline(line_id="victoria", day=day),
        ttl_seconds=60,
    )
    cache.clear()

    assert cache.get(line_id="victoria", day=day) is None


def test_oldest_timeline_is_evicted_when_cache_is_full() -> None:
    cache = DailyTimelineCache(max_entries=2)
    day = date(2026, 6, 11)

    for line_id in ("victoria", "central", "jubilee"):
        cache.set(
            line_id=line_id,
            day=day,
            value=_timeline(line_id=line_id, day=day),
            ttl_seconds=60,
        )

    assert cache.get(line_id="victoria", day=day) is None
    assert cache.get(line_id="central", day=day) is not None
    assert cache.get(line_id="jubilee", day=day) is not None


def test_disruption_summary_is_cached_by_date() -> None:
    cache = DailyDisruptionSummaryCache()
    first_day = date(2026, 6, 10)
    second_day = date(2026, 6, 11)
    summary = DailyDisruptionSummaryRead(
        date=first_day,
        timezone="Europe/London",
        lines={
            "circle": LineDisruptionSummaryRead(
                disrupted=True,
                disruption_count=1,
                latest_disruption_at=datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
            ),
            "northern": LineDisruptionSummaryRead(
                disrupted=False,
                disruption_count=0,
                latest_disruption_at=None,
            ),
        },
    )

    cache.set(day=first_day, value=summary, ttl_seconds=60)

    assert cache.get(day=first_day) == summary
    assert cache.get(day=second_day) is None


def test_expired_disruption_summary_is_removed() -> None:
    clock = FakeClock()
    cache = DailyDisruptionSummaryCache(clock=clock)
    day = date(2026, 6, 11)

    cache.set(
        day=day,
        value=DailyDisruptionSummaryRead(
            date=day,
            timezone="Europe/London",
            lines={
                "circle": LineDisruptionSummaryRead(
                    disrupted=True,
                    disruption_count=1,
                    latest_disruption_at=datetime(2026, 6, 11, 8, 0, tzinfo=UTC),
                )
            },
        ),
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(day=day) is None
