import httpx

from app.clients.tfl import TFL_RAIL_MODES, TflClient


def mock_client(response_json: list[dict]) -> TflClient:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    return TflClient(transport=httpx.MockTransport(handler))


async def test_get_rail_line_statuses_requests_all_supported_modes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        requested_modes = request.url.path.split("/")[3].split(",")
        assert requested_modes == list(TFL_RAIL_MODES)
        assert "elizabeth-line" in requested_modes
        return httpx.Response(200, json=[])

    client = TflClient(transport=httpx.MockTransport(handler))
    try:
        await client.get_rail_line_statuses()
    finally:
        await client.close()


async def test_get_rail_line_statuses_parses_line_and_status_fields() -> None:
    client = mock_client(
        [
            {
                "id": "elizabeth",
                "name": "Elizabeth line",
                "modeName": "elizabeth-line",
                "lineStatuses": [
                    {
                        "statusSeverity": 9,
                        "statusSeverityDescription": "Minor Delays",
                        "reason": "Signal failure",
                    }
                ],
            }
        ]
    )

    try:
        lines = await client.get_rail_line_statuses()
    finally:
        await client.close()

    assert len(lines) == 1
    assert lines[0].id == "elizabeth"
    assert lines[0].name == "Elizabeth line"
    assert lines[0].mode_name == "elizabeth-line"
    assert len(lines[0].statuses) == 1
    assert lines[0].statuses[0].status_severity == 9
    assert lines[0].statuses[0].status_description == "Minor Delays"
    assert lines[0].statuses[0].reason == "Signal failure"


async def test_get_rail_line_statuses_normalizes_and_deduplicates_statuses() -> None:
    client = mock_client(
        [
            {
                "id": "victoria",
                "name": "Victoria",
                "modeName": "tube",
                "lineStatuses": [
                    {
                        "statusSeverity": 10,
                        "statusSeverityDescription": " Good Service\n",
                        "reason": " \n",
                    },
                    {
                        "statusSeverity": 10,
                        "statusSeverityDescription": "Good Service",
                    },
                    {
                        "statusSeverity": 10,
                        "statusSeverityDescription": "Good Service",
                        "reason": " Different reason\n",
                    },
                ],
            }
        ]
    )

    try:
        lines = await client.get_rail_line_statuses()
    finally:
        await client.close()

    statuses = lines[0].statuses
    assert len(statuses) == 2
    assert statuses[0].status_description == "Good Service"
    assert statuses[0].reason is None
    assert statuses[1].reason == "Different reason"
