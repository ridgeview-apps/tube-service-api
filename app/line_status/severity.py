from enum import IntEnum


class TflRailStatusSeverity(IntEnum):
    SPECIAL_SERVICE = 0
    CLOSED = 1
    SUSPENDED = 2
    PART_SUSPENDED = 3
    PLANNED_CLOSURE = 4
    PART_CLOSURE = 5
    SEVERE_DELAYS = 6
    REDUCED_SERVICE = 7
    BUS_SERVICE = 8
    MINOR_DELAYS = 9
    GOOD_SERVICE = 10


DISRUPTION_SEVERITIES = frozenset(
    {
        TflRailStatusSeverity.SPECIAL_SERVICE,
        TflRailStatusSeverity.CLOSED,
        TflRailStatusSeverity.SUSPENDED,
        TflRailStatusSeverity.PART_SUSPENDED,
        TflRailStatusSeverity.PART_CLOSURE,
        TflRailStatusSeverity.SEVERE_DELAYS,
        TflRailStatusSeverity.REDUCED_SERVICE,
        TflRailStatusSeverity.BUS_SERVICE,
        TflRailStatusSeverity.MINOR_DELAYS,
    }
)

TIMELINE_SEVERITIES = DISRUPTION_SEVERITIES | {
    TflRailStatusSeverity.PLANNED_CLOSURE,
    TflRailStatusSeverity.GOOD_SERVICE,
}
