import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.http_debug import HttpDebugMiddleware


async def test_http_debug_middleware_logs_response_without_consuming_body(caplog) -> None:
    app = FastAPI()
    app.add_middleware(HttpDebugMiddleware, body_limit=12)

    @app.get("/debug")
    async def debug() -> dict[str, str]:
        return {"message": "hello world"}

    caplog.set_level(logging.INFO, logger="uvicorn.error.http")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/debug")

    assert response.status_code == 200
    assert response.json() == {"message": "hello world"}
    assert len(caplog.records) == 1
    assert "GET /debug -> 200" in caplog.text
    assert "application/json" in caplog.text
    assert """body='{"message":"...'""" in caplog.text
