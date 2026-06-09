import httpx

from app.clients.tfl import TFL_RAIL_MODES, TflClient


async def test_get_rail_line_statuses_includes_elizabeth_line() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        requested_modes = request.url.path.split("/")[3].split(",")
        assert requested_modes == list(TFL_RAIL_MODES)
        assert "elizabeth-line" in requested_modes

        return httpx.Response(
            200,
            json=[
                {
                    "id": "elizabeth",
                    "name": "Elizabeth line",
                    "modeName": "elizabeth-line",
                    "lineStatuses": [
                        {
                            "statusSeverity": 10,
                            "statusSeverityDescription": "Good Service",
                        }
                    ],
                }
            ],
        )

    client = TflClient(transport=httpx.MockTransport(handler))
    try:
        statuses = await client.get_rail_line_statuses()
    finally:
        await client.close()

    assert len(statuses) == 1
    assert statuses[0].line_id == "elizabeth"
    assert statuses[0].mode_name == "elizabeth-line"
    assert statuses[0].reason is None
