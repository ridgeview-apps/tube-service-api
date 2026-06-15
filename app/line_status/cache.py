from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import monotonic

from app.line_status.schemas import DailyDisruptionSummaryRead, DailyTimelineRead

type TimelineCacheKey = tuple[str, date]


@dataclass
class _CacheEntry:
    value: DailyTimelineRead
    expires_at: float


@dataclass
class _DisruptionSummaryCacheEntry:
    value: DailyDisruptionSummaryRead
    expires_at: float


class DailyTimelineCache:
    def __init__(
        self,
        *,
        max_entries: int = 512,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._entries: dict[TimelineCacheKey, _CacheEntry] = {}
        self._max_entries = max_entries
        self._clock = clock

    def get(
        self,
        *,
        line_id: str,
        operational_date: date,
    ) -> DailyTimelineRead | None:
        key = (line_id, operational_date)
        entry = self._entries.get(key)
        if entry is None:
            return None

        if entry.expires_at <= self._clock():
            del self._entries[key]
            return None

        return entry.value

    def set(
        self,
        *,
        line_id: str,
        operational_date: date,
        value: DailyTimelineRead,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return

        self._remove_expired_entries()
        key = (line_id, operational_date)
        if key not in self._entries and len(self._entries) >= self._max_entries:
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]

        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=self._clock() + ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

    def _remove_expired_entries(self) -> None:
        current_time = self._clock()
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expires_at <= current_time
        ]
        for key in expired_keys:
            del self._entries[key]


class DailyDisruptionSummaryCache:
    def __init__(
        self,
        *,
        max_entries: int = 32,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._entries: dict[date, _DisruptionSummaryCacheEntry] = {}
        self._max_entries = max_entries
        self._clock = clock

    def get(self, *, operational_date: date) -> DailyDisruptionSummaryRead | None:
        entry = self._entries.get(operational_date)
        if entry is None:
            return None

        if entry.expires_at <= self._clock():
            del self._entries[operational_date]
            return None

        return entry.value

    def set(
        self,
        *,
        operational_date: date,
        value: DailyDisruptionSummaryRead,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return

        self._remove_expired_entries()
        if operational_date not in self._entries and len(self._entries) >= self._max_entries:
            oldest_operational_date = next(iter(self._entries))
            del self._entries[oldest_operational_date]

        self._entries[operational_date] = _DisruptionSummaryCacheEntry(
            value=value,
            expires_at=self._clock() + ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

    def _remove_expired_entries(self) -> None:
        current_time = self._clock()
        expired_operational_dates = [
            operational_date
            for operational_date, entry in self._entries.items()
            if entry.expires_at <= current_time
        ]
        for operational_date in expired_operational_dates:
            del self._entries[operational_date]


daily_timeline_cache = DailyTimelineCache()
daily_disruption_summary_cache = DailyDisruptionSummaryCache()
