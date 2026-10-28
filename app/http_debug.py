import json
import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("uvicorn.error.http")

SENSITIVE_JSON_FIELDS = frozenset(
    {
        "api_key",
        "apns_private_key",
        "authorization",
        "client_api_keys",
        "password",
        "push_token",
        "secret",
        "token",
    }
)
REDACTED_VALUE = "[REDACTED]"


class HttpDebugMiddleware:
    def __init__(self, app: ASGIApp, body_limit: int = 4096) -> None:
        self.app = app
        self.body_limit = body_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        request_body = bytearray()
        response_body = bytearray()
        started_at = perf_counter()

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request" and self.body_limit > 0:
                chunk = message.get("body", b"")
                remaining = self.body_limit - len(request_body)
                if remaining > 0:
                    request_body.extend(chunk[:remaining])
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_headers, status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body" and self.body_limit > 0:
                chunk = message.get("body", b"")
                remaining = self.body_limit - len(response_body)
                if remaining > 0:
                    response_body.extend(chunk[:remaining])

            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            duration_ms = (perf_counter() - started_at) * 1000
            request_header_map = {
                key.decode().lower(): value.decode() for key, value in scope["headers"]
            }
            response_header_map = {
                key.decode().lower(): value.decode() for key, value in response_headers
            }
            request_body_text = _format_body(
                bytes(request_body),
                content_type=request_header_map.get("content-type", ""),
                is_truncated=_is_truncated(request_header_map, request_body),
            )
            content_length = response_header_map.get("content-length")
            try:
                response_length = (
                    int(content_length) if content_length is not None else len(response_body)
                )
            except ValueError:
                response_length = len(response_body)
            response_body_text = _format_body(
                bytes(response_body),
                content_type=response_header_map.get("content-type", ""),
                is_truncated=response_length > len(response_body),
            )

            logger.info(
                "%s %s -> %s %.1fms request_body=%s response_body=%s",
                scope["method"],
                scope["path"],
                status_code,
                duration_ms,
                request_body_text,
                response_body_text,
            )


def _is_truncated(headers: dict[str, str], body: bytearray) -> bool:
    content_length = headers.get("content-length")
    try:
        return content_length is not None and int(content_length) > len(body)
    except ValueError:
        return False


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
    return "\n" + json.dumps(_redact_sensitive_json(parsed_body), indent=2)


def _redact_sensitive_json(value: object) -> object:
    if isinstance(value, list):
        return [_redact_sensitive_json(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: (
            REDACTED_VALUE
            if isinstance(key, str) and key.lower().replace("-", "_") in SENSITIVE_JSON_FIELDS
            else _redact_sensitive_json(nested_value)
        )
        for key, nested_value in value.items()
    }
