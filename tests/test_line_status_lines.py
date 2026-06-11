from app.line_status.lines import SUPPORTED_LINE_IDS


def test_supported_line_ids_cover_all_configured_rail_modes() -> None:
    assert (
        frozenset(
            {
                "bakerloo",
                "central",
                "circle",
                "district",
                "dlr",
                "elizabeth",
                "hammersmith-city",
                "jubilee",
                "liberty",
                "lioness",
                "metropolitan",
                "mildmay",
                "northern",
                "piccadilly",
                "suffragette",
                "tram",
                "victoria",
                "waterloo-city",
                "weaver",
                "windrush",
            }
        )
        == SUPPORTED_LINE_IDS
    )
