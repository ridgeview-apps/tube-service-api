from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.notifications.apns import (
    APNsConfig,
    APNsPushSender,
    APNsRequest,
    APNsResponse,
    apns_response_to_send_result,
    build_apns_payload,
)
from app.notifications.events import NotificationEventType
from app.notifications.models import NotificationDelivery, NotificationEvent
from app.notifications.schemas import PushPlatform
from app.notifications.sender import (
    NoopPushSender,
    PushSendStatus,
    build_configured_push_sender,
)


class CapturingAPNsTransport:
    def __init__(self, response: APNsResponse) -> None:
        self.response = response
        self.requests: list[APNsRequest] = []

    async def send(self, request: APNsRequest) -> APNsResponse:
        self.requests.append(request)
        return self.response


def delivery(*, platform: PushPlatform = PushPlatform.IOS) -> NotificationDelivery:
    return NotificationDelivery(
        id=42,
        event_id=7,
        device_id="install-123",
        platform=platform.value,
        push_token="push-token",
        app_variant="production",
        status="pending",
        created_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
    )


def delivery_with_variant(app_variant: str) -> NotificationDelivery:
    notification_delivery = delivery()
    notification_delivery.app_variant = app_variant
    return notification_delivery


def event(
    *,
    line_id: str = "victoria",
    event_type: NotificationEventType = NotificationEventType.DISRUPTION_STARTED,
    reason: str | None = "Signal failure",
) -> NotificationEvent:
    return NotificationEvent(
        id=7,
        dedupe_key="event-key",
        line_id=line_id,
        event_type=event_type.value,
        observed_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
        severity=6,
        status_description="Severe Delays",
        reason=reason,
        created_at=datetime(2026, 6, 16, 8, 0, tzinfo=UTC),
    )


def config() -> APNsConfig:
    return APNsConfig(
        team_id="TEAMID1234",
        key_id="KEYID1234",
        bundle_ids={
            "production": "uk.example.tube-service",
            "beta": "uk.example.tube-service.beta",
        },
        private_key="unused-in-tests",
        use_sandbox=True,
    )


def test_build_apns_payload_contains_alert_and_safe_metadata() -> None:
    payload = build_apns_payload(delivery=delivery(), event=event())

    assert payload == {
        "aps": {
            "alert": {
                "title": "Victoria line disruption",
                "body": "Severe Delays: Signal failure",
            },
            "sound": "default",
        },
        "delivery_id": 42,
        "event_id": 7,
        "line_id": "victoria",
        "event_type": "disruption_started",
        "severity": 6,
        "observed_at": "2026-06-16T08:00:00+00:00",
    }
    assert "push-token" not in str(payload)


def test_build_apns_payload_for_recovery_event() -> None:
    payload = build_apns_payload(
        delivery=delivery(),
        event=event(event_type=NotificationEventType.SERVICE_RESUMED, reason=None),
    )

    assert payload["aps"]["alert"] == {
        "title": "Victoria line",
        "body": "A good service has resumed.",
    }


@pytest.mark.parametrize(
    ("line_id", "title"),
    [
        ("hammersmith-city", "Hammersmith & City line disruption"),
        ("waterloo-city", "Waterloo & City line disruption"),
        ("dlr", "DLR disruption"),
        ("tram", "Tram disruption"),
    ],
)
def test_build_apns_payload_formats_line_name_exceptions(line_id: str, title: str) -> None:
    payload = build_apns_payload(delivery=delivery(), event=event(line_id=line_id))

    assert payload["aps"]["alert"]["title"] == title


def test_apns_response_handling_for_success() -> None:
    result = apns_response_to_send_result(APNsResponse(status_code=200, apns_id="apns-id"))

    assert result.status == PushSendStatus.SENT
    assert result.provider_message_id == "apns-id"
    assert result.failure_reason is None


@pytest.mark.parametrize("reason", ["BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"])
def test_apns_response_handling_for_invalid_or_expired_tokens(reason: str) -> None:
    result = apns_response_to_send_result(APNsResponse(status_code=410, reason=reason))

    assert result.status == PushSendStatus.FAILED
    assert result.failure_reason == "Invalid or expired push token"


def test_apns_response_handling_for_provider_failure() -> None:
    result = apns_response_to_send_result(APNsResponse(status_code=503, reason="Shutdown"))

    assert result.status == PushSendStatus.FAILED
    assert result.failure_reason == "APNs provider failed: Shutdown"


async def test_apns_sender_sends_request_without_hitting_apns() -> None:
    transport = CapturingAPNsTransport(APNsResponse(status_code=200, apns_id="apns-id"))
    sender = APNsPushSender(
        config=config(),
        transport=transport,
        token_provider=lambda: "provider-token",
    )

    result = await sender.send(delivery=delivery(), event=event())

    assert result.status == PushSendStatus.SENT
    [request] = transport.requests
    assert request.device_token == "push-token"
    assert request.headers == {
        "authorization": "bearer provider-token",
        "apns-topic": "uk.example.tube-service",
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    assert request.payload["aps"]["alert"]["title"] == "Victoria line disruption"


async def test_apns_sender_uses_bundle_id_for_delivery_app_variant() -> None:
    transport = CapturingAPNsTransport(APNsResponse(status_code=200, apns_id="apns-id"))
    sender = APNsPushSender(
        config=config(),
        transport=transport,
        token_provider=lambda: "provider-token",
    )

    result = await sender.send(
        delivery=delivery_with_variant("beta"),
        event=event(),
    )

    assert result.status == PushSendStatus.SENT
    [request] = transport.requests
    assert request.headers["apns-topic"] == "uk.example.tube-service.beta"


async def test_apns_sender_fails_when_delivery_app_variant_is_not_configured() -> None:
    transport = CapturingAPNsTransport(APNsResponse(status_code=200, apns_id="apns-id"))
    sender = APNsPushSender(
        config=config(),
        transport=transport,
        token_provider=lambda: "provider-token",
    )

    result = await sender.send(
        delivery=delivery_with_variant("unknown"),
        event=event(),
    )

    assert result.status == PushSendStatus.FAILED
    assert result.failure_reason == "APNs bundle ID is not configured for app variant: unknown"
    assert transport.requests == []


async def test_apns_sender_skips_non_ios_delivery() -> None:
    transport = CapturingAPNsTransport(APNsResponse(status_code=200, apns_id="apns-id"))
    sender = APNsPushSender(
        config=config(),
        transport=transport,
        token_provider=lambda: "provider-token",
    )

    result = await sender.send(delivery=delivery(platform=PushPlatform.ANDROID), event=event())

    assert result.status == PushSendStatus.SKIPPED
    assert result.failure_reason == "Unsupported push platform"
    assert transport.requests == []


def test_configured_sender_uses_noop_when_apns_config_is_missing() -> None:
    sender = build_configured_push_sender(Settings())

    assert isinstance(sender, NoopPushSender)


def test_configured_sender_uses_apns_when_configured() -> None:
    sender = build_configured_push_sender(
        Settings(
            apns_team_id="TEAMID1234",
            apns_key_id="KEYID1234",
            apns_bundle_id="uk.example.tube-service",
            apns_private_key="private-key",
        )
    )

    assert isinstance(sender, APNsPushSender)


def test_configured_sender_uses_apns_bundle_ids_when_configured() -> None:
    sender = build_configured_push_sender(
        Settings(
            apns_team_id="TEAMID1234",
            apns_key_id="KEYID1234",
            apns_bundle_ids={
                "production": "uk.example.tube-service",
                "beta": "uk.example.tube-service.beta",
            },
            apns_private_key="private-key",
        )
    )

    assert isinstance(sender, APNsPushSender)
