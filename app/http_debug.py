import json
import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("uvicorn.error.http")


class HttpDebugMiddleware:
    def __init__(self, app: ASGIApp, body_limit: int = 4096) -> None:
        self.app = app
        self.body_limit = body_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        headers: list[tuple[bytes, bytes]] = []
        body = bytearray()
        started_at = perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal headers, status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.get("headers", [])
            elif message["type"] == "http.response.body" and self.body_limit > 0:
                chunk = message.get("body", b"")
                remaining = self.body_limit - len(body)
                if remaining > 0:
                    body.extend(chunk[:remaining])

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (perf_counter() - started_at) * 1000
            header_map = {key.decode().lower(): value.decode() for key, value in headers}
            content_length = header_map.get("content-length")
            try:
                response_length = int(content_length) if content_length is not None else len(body)
            except ValueError:
                response_length = len(body)
            is_truncated = response_length > len(body)
            body_text = _format_body(
                bytes(body),
                content_type=header_map.get("content-type", ""),
                is_truncated=is_truncated,
            )

            logger.info(
                "%s %s -> %s %.1fms %s body=%s",
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
                header_map.get("content-type", ""),
                body_text,
            )


def _format_body(body: bytes, *, content_type: str, is_truncated: bool) -> str:
    body_text = body.decode(errors="replace")
    if is_truncated:
        return f"{body_text!r}..."
    if "json" not in content_type.lower():
        return repr(body_text)
    try:
        parsed_body = json.loads(body_text)
    except json.JSONDecodeError:
        return repr(body_text)
    return "\n" + json.dumps(parsed_body, indent=2)
