from dataclasses import dataclass

import httpx

TFL_RAIL_MODES = ("tube", "elizabeth-line", "dlr", "overground", "tram")


@dataclass(frozen=True)
class TflLineStatus:
    line_id: str
    line_name: str
    mode_name: str
    status_severity: int
    status_description: str
    reason: str | None


class TflClient:
    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        params = {"app_key": api_key} if api_key else None
        self._client = httpx.AsyncClient(
            base_url="https://api.tfl.gov.uk",
            params=params,
            timeout=20,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_rail_line_statuses(self) -> list[TflLineStatus]:
        modes = ",".join(TFL_RAIL_MODES)
        response = await self._client.get(f"/Line/Mode/{modes}/Status")
        response.raise_for_status()

        statuses: list[TflLineStatus] = []
        for line in response.json():
            for status in line.get("lineStatuses", []):
                statuses.append(
                    TflLineStatus(
                        line_id=line["id"],
                        line_name=line["name"],
                        mode_name=line["modeName"],
                        status_severity=status["statusSeverity"],
                        status_description=status["statusSeverityDescription"],
                        reason=status.get("reason"),
                    )
                )
        return statuses
