from app.line_status.severity import (
    DISRUPTION_SEVERITIES,
    TIMELINE_SEVERITIES,
    TflRailStatusSeverity,
)


def test_disruption_severities_exclude_planned_closure_and_good_service() -> None:
    assert (
        frozenset(
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
        == DISRUPTION_SEVERITIES
    )
    assert TflRailStatusSeverity.PLANNED_CLOSURE not in DISRUPTION_SEVERITIES
    assert TflRailStatusSeverity.GOOD_SERVICE not in DISRUPTION_SEVERITIES


def test_timeline_severities_include_disruptions_planned_closure_and_good_service() -> None:
    assert (
        DISRUPTION_SEVERITIES
        | {
            TflRailStatusSeverity.PLANNED_CLOSURE,
            TflRailStatusSeverity.GOOD_SERVICE,
        }
        == TIMELINE_SEVERITIES
    )
