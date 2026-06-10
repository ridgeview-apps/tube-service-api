from dataclasses import dataclass

import httpx

TFL_RAIL_MODES = ("tube", "elizabeth-line", "dlr", "overground", "tram")


@dataclass(frozen=True)
class TflLineStatus:
    status_severity: int
    status_description: str
    reason: str | None


@dataclass(frozen=True)
class TflLine:
    id: str
    name: str
    mode_name: str
    statuses: list[TflLineStatus]


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

    async def get_rail_line_statuses(self) -> list[TflLine]:
        modes = ",".join(TFL_RAIL_MODES)
        response = await self._client.get(f"/Line/Mode/{modes}/Status")
        response.raise_for_status()

        lines: list[TflLine] = []
        for line in response.json():
            lines.append(
                TflLine(
                    id=line["id"],
                    name=line["name"],
                    mode_name=line["modeName"],
                    statuses=self._parse_unique_statuses(line.get("lineStatuses", [])),
                )
            )
        return lines

    @staticmethod
    def _parse_unique_statuses(raw_statuses: list[dict]) -> list[TflLineStatus]:
        statuses: list[TflLineStatus] = []
        seen: set[TflLineStatus] = set()

        for raw_status in raw_statuses:
            reason = raw_status.get("reason")
            normalized_reason = reason.strip() or None if reason is not None else None
            status = TflLineStatus(
                status_severity=raw_status["statusSeverity"],
                status_description=raw_status["statusSeverityDescription"].strip(),
                reason=normalized_reason,
            )

            if status not in seen:
                seen.add(status)
                statuses.append(status)

        return statuses
