from datetime import date

from app.line_status.cache import DailyDisruptionSummaryCache, DailyHistoryCache
from app.line_status.schemas import DailyHistoryRead, LineDisruptionSummaryRead


class FakeClock:
    def __init__(self) -> None:
        self.current_time = 0.0

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


def _history(*, line_id: str, day: date) -> DailyHistoryRead:
    return DailyHistoryRead(
        line_id=line_id,
        date=day,
        timezone="Europe/London",
        snapshots=[],
    )


def test_stored_history_can_be_retrieved() -> None:
    cache = DailyHistoryCache()
    day = date(2026, 6, 11)
    history = _history(line_id="victoria", day=day)

    cache.set(
        line_id="victoria",
        day=day,
        value=history,
        ttl_seconds=60,
    )

    assert cache.get(line_id="victoria", day=day) == history


def test_line_and_date_are_separate_cache_keys() -> None:
    cache = DailyHistoryCache()
    first_day = date(2026, 6, 10)
    second_day = date(2026, 6, 11)
    victoria_history = _history(line_id="victoria", day=first_day)
    central_history = _history(line_id="central", day=first_day)

    cache.set(
        line_id="victoria",
        day=first_day,
        value=victoria_history,
        ttl_seconds=60,
    )
    cache.set(
        line_id="central",
        day=first_day,
        value=central_history,
        ttl_seconds=60,
    )

    assert cache.get(line_id="victoria", day=first_day) == victoria_history
    assert cache.get(line_id="central", day=first_day) == central_history
    assert cache.get(line_id="victoria", day=second_day) is None


def test_expired_history_is_removed() -> None:
    clock = FakeClock()
    cache = DailyHistoryCache(clock=clock)
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_history(line_id="victoria", day=day),
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(line_id="victoria", day=day) is None


def test_zero_ttl_does_not_store_history() -> None:
    cache = DailyHistoryCache()
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_history(line_id="victoria", day=day),
        ttl_seconds=0,
    )

    assert cache.get(line_id="victoria", day=day) is None


def test_clear_removes_all_history() -> None:
    cache = DailyHistoryCache()
    day = date(2026, 6, 11)

    cache.set(
        line_id="victoria",
        day=day,
        value=_history(line_id="victoria", day=day),
        ttl_seconds=60,
    )
    cache.clear()

    assert cache.get(line_id="victoria", day=day) is None


def test_oldest_history_is_evicted_when_cache_is_full() -> None:
    cache = DailyHistoryCache(max_entries=2)
    day = date(2026, 6, 11)

    for line_id in ("victoria", "central", "jubilee"):
        cache.set(
            line_id=line_id,
            day=day,
            value=_history(line_id=line_id, day=day),
            ttl_seconds=60,
        )

    assert cache.get(line_id="victoria", day=day) is None
    assert cache.get(line_id="central", day=day) is not None
    assert cache.get(line_id="jubilee", day=day) is not None


def test_disruption_summary_is_cached_by_date() -> None:
    cache = DailyDisruptionSummaryCache()
    first_day = date(2026, 6, 10)
    second_day = date(2026, 6, 11)
    summary = [
        LineDisruptionSummaryRead(line_id="circle", disrupted=True),
        LineDisruptionSummaryRead(line_id="northern", disrupted=False),
    ]

    cache.set(day=first_day, value=summary, ttl_seconds=60)

    assert cache.get(day=first_day) == summary
    assert cache.get(day=second_day) is None


def test_expired_disruption_summary_is_removed() -> None:
    clock = FakeClock()
    cache = DailyDisruptionSummaryCache(clock=clock)
    day = date(2026, 6, 11)

    cache.set(
        day=day,
        value=[LineDisruptionSummaryRead(line_id="circle", disrupted=True)],
        ttl_seconds=60,
    )
    clock.advance(60)

    assert cache.get(day=day) is None
