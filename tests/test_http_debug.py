import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.http_debug import HttpDebugMiddleware


async def test_http_debug_middleware_logs_request_and_response_without_consuming_body(
    caplog,
) -> None:
    app = FastAPI()
    app.add_middleware(HttpDebugMiddleware)

    @app.post("/debug")
    async def debug(body: dict[str, str]) -> dict[str, str]:
        return body

    caplog.set_level(logging.INFO, logger="uvicorn.error.http")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/debug", json={"message": "hello world"})

    assert response.status_code == 200
    assert response.json() == {"message": "hello world"}
    assert len(caplog.records) == 1
    assert "POST /debug -> 200" in caplog.text
    assert 'request_body=\n{\n  "message": "hello world"\n}' in caplog.text
    assert 'response_body=\n{\n  "message": "hello world"\n}' in caplog.text


async def test_http_debug_middleware_redacts_sensitive_request_fields(caplog) -> None:
    app = FastAPI()
    app.add_middleware(HttpDebugMiddleware)

    @app.post("/debug")
    async def debug(body: dict[str, str]) -> dict[str, str]:
        return body

    caplog.set_level(logging.INFO, logger="uvicorn.error.http")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/debug", json={"push_token": "private-token"})

    assert response.status_code == 200
    assert "private-token" not in caplog.text
    assert '"push_token": "[REDACTED]"' in caplog.text


async def test_http_debug_middleware_keeps_truncated_body_compact(caplog) -> None:
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
    assert """response_body='{"message":"'...""" in caplog.text
