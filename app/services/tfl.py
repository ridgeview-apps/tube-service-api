from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TflLineStatus:
    line_id: str
    line_name: str
    mode_name: str
    status_severity: int
    status_description: str
    reason: str | None


class TflClient:
    def __init__(self, api_key: str | None = None) -> None:
        params = {"app_key": api_key} if api_key else None
        self._client = httpx.AsyncClient(
            base_url="https://api.tfl.gov.uk",
            params=params,
            timeout=20,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_tube_line_statuses(self) -> list[TflLineStatus]:
        response = await self._client.get("/Line/Mode/tube/Status")
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
