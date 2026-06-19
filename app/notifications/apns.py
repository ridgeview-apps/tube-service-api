import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings
from app.notifications.models import NotificationDelivery, NotificationEvent
from app.notifications.schemas import PushPlatform
from app.notifications.sender import PushSender, PushSendResult, PushSendStatus

APNS_INVALID_TOKEN_REASONS = {
    "BadDeviceToken",
    "DeviceTokenNotForTopic",
    "Unregistered",
}


@dataclass(frozen=True)
class APNsConfig:
    team_id: str
    key_id: str
    bundle_id: str
    private_key: str
    use_sandbox: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> "APNsConfig | None":
        if not settings.apns_is_configured or settings.apns_private_key is None:
            return None
        return cls(
            team_id=settings.apns_team_id or "",
            key_id=settings.apns_key_id or "",
            bundle_id=settings.apns_bundle_id or "",
            private_key=settings.apns_private_key.get_secret_value().replace("\\n", "\n"),
            use_sandbox=settings.apns_use_sandbox,
        )


@dataclass(frozen=True)
class APNsRequest:
    device_token: str
    headers: dict[str, str]
    payload: dict[str, object]


@dataclass(frozen=True)
class APNsResponse:
    status_code: int
    apns_id: str | None = None
    reason: str | None = None


class APNsTransport(Protocol):
    async def send(self, request: APNsRequest) -> APNsResponse:
        pass


class HttpxAPNsTransport:
    def __init__(self, *, use_sandbox: bool) -> None:
        host = "api.sandbox.push.apple.com" if use_sandbox else "api.push.apple.com"
        self._base_url = f"https://{host}/3/device"

    async def send(self, request: APNsRequest) -> APNsResponse:
        async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/{request.device_token}",
                headers=request.headers,
                json=request.payload,
            )

        reason = None
        if response.content:
            try:
                reason = response.json().get("reason")
            except json.JSONDecodeError:
                reason = None
        return APNsResponse(
            status_code=response.status_code,
            apns_id=response.headers.get("apns-id"),
            reason=reason,
        )


class APNsPushSender(PushSender):
    def __init__(
        self,
        *,
        config: APNsConfig,
        transport: APNsTransport | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or HttpxAPNsTransport(use_sandbox=config.use_sandbox)
        self._token_provider = token_provider or APNsAuthTokenProvider(config=config)

    async def send(
        self,
        *,
        delivery: NotificationDelivery,
        event: NotificationEvent,
    ) -> PushSendResult:
        if delivery.platform != PushPlatform.IOS.value:
            return PushSendResult(
                status=PushSendStatus.SKIPPED,
                failure_reason="Unsupported push platform",
            )

        response = await self._transport.send(
            APNsRequest(
                device_token=delivery.push_token,
                headers=self._headers(),
                payload=build_apns_payload(delivery=delivery, event=event),
            )
        )
        return apns_response_to_send_result(response)

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"bearer {self._token_provider()}",
            "apns-topic": self._config.bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }


class APNsAuthTokenProvider:
    def __init__(self, *, config: APNsConfig, clock: Callable[[], float] = time.time) -> None:
        self._config = config
        self._clock = clock
        self._cached_token: str | None = None
        self._cached_at = 0

    def __call__(self) -> str:
        now = int(self._clock())
        if self._cached_token is not None and now - self._cached_at < 50 * 60:
            return self._cached_token

        token = _create_provider_token(
            team_id=self._config.team_id,
            key_id=self._config.key_id,
            private_key=self._config.private_key,
            issued_at=now,
        )
        self._cached_token = token
        self._cached_at = now
        return token


def build_apns_payload(
    *,
    delivery: NotificationDelivery,
    event: NotificationEvent,
) -> dict[str, object]:
    if event.event_type == "test":
        return build_test_apns_payload(device_id=delivery.device_id)

    line_name = _line_display_name(event.line_id)
    title = (
        f"{line_name} line recovered"
        if event.event_type == "service_resumed"
        else f"{line_name} line disruption"
    )
    body = event.status_description
    if event.reason:
        body = f"{body}: {event.reason}"

    return {
        "aps": {
            "alert": {
                "title": title,
                "body": body,
            },
            "sound": "default",
        },
        "delivery_id": delivery.id,
        "event_id": event.id,
        "line_id": event.line_id,
        "event_type": event.event_type,
        "severity": event.severity,
        "observed_at": event.observed_at.isoformat(),
    }


def build_test_apns_payload(*, device_id: str) -> dict[str, object]:
    return {
        "aps": {
            "alert": {
                "title": "Tube Service test notification",
                "body": "Push notifications are configured for this device.",
            },
            "sound": "default",
        },
        "test": True,
        "device_id": device_id,
    }


def apns_response_to_send_result(response: APNsResponse) -> PushSendResult:
    if response.status_code == 200:
        return PushSendResult(
            status=PushSendStatus.SENT,
            provider_message_id=response.apns_id,
        )
    if response.reason in APNS_INVALID_TOKEN_REASONS:
        return PushSendResult(
            status=PushSendStatus.FAILED,
            failure_reason="Invalid or expired push token",
        )
    return PushSendResult(
        status=PushSendStatus.FAILED,
        failure_reason=f"APNs provider failed: {response.reason or response.status_code}",
    )


def _create_provider_token(
    *,
    team_id: str,
    key_id: str,
    private_key: str,
    issued_at: int,
) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    header = _base64url_json({"alg": "ES256", "kid": key_id})
    claims = _base64url_json({"iss": team_id, "iat": issued_at})
    signing_input = f"{header}.{claims}".encode()
    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    signature = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    encoded_signature = _base64url(raw_signature)
    return f"{header}.{claims}.{encoded_signature}"


def _base64url_json(value: dict[str, object]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":")).encode())


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _line_display_name(line_id: str) -> str:
    if line_id == "dlr":
        return "DLR"
    return line_id.replace("-", " ").title()
