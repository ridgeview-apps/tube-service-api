from httpx import ASGITransport, AsyncClient

from app.api.routes import health
from app.main import app


async def test_health() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class SuccessfulConnection:
    async def __aenter__(self) -> "SuccessfulConnection":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        assert str(statement) == "SELECT 1"


class SuccessfulEngine:
    def connect(self) -> SuccessfulConnection:
        return SuccessfulConnection()


class UnavailableConnection:
    async def __aenter__(self) -> "UnavailableConnection":
        raise OSError("database host is unavailable")

    async def __aexit__(self, *_: object) -> None:
        return None


class UnavailableEngine:
    def connect(self) -> UnavailableConnection:
        return UnavailableConnection()


async def test_ready_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr(health, "engine", SuccessfulEngine())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_ready_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(health, "engine", UnavailableEngine())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "unavailable"}}
