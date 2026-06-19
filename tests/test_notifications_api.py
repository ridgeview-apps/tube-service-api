import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes.notifications import get_push_sender
from app.api.security import require_api_key
from app.config import Settings, get_settings
from app.database import Base, get_session
from app.main import app
from app.notifications.sender import PushSendResult, PushSendStatus

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    poolclass=StaticPool,
)
db_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


async def get_test_session():
    async with db_session_factory() as session:
        yield session


async def bypass_api_key() -> None:
    pass


class FakePushSender:
    def __init__(self) -> None:
        self.delivery_device_ids: list[str] = []
        self.event_types: list[str] = []

    async def send(self, *, delivery, event) -> PushSendResult:
        self.delivery_device_ids.append(delivery.device_id)
        self.event_types.append(event.event_type)
        return PushSendResult(
            status=PushSendStatus.SENT,
            provider_message_id="test-apns-id",
        )


@pytest.fixture(autouse=True)
async def clean_database():
    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[require_api_key] = bypass_api_key
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.clear()


async def test_registers_notification_device_idempotently() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_response = await client.put(
            "/v1/notification-devices/install-123",
            json={
                "platform": "ios",
                "push_token": "first-token",
                "app_version": "1.0.0",
            },
        )
        second_response = await client.put(
            "/v1/notification-devices/install-123",
            json={
                "platform": "ios",
                "push_token": "rotated-token",
                "app_version": "1.1.0",
            },
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert "push_token" not in second_response.json()
    assert second_response.json()["device_id"] == "install-123"
    assert second_response.json()["platform"] == "ios"
    assert second_response.json()["enabled"] is True
    assert second_response.json()["app_version"] == "1.1.0"


async def test_reassigns_push_token_to_latest_device_registration() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_response = await client.put(
            "/v1/notification-devices/old-install",
            json={"platform": "ios", "push_token": "shared-token"},
        )
        second_response = await client.put(
            "/v1/notification-devices/new-install",
            json={"platform": "ios", "push_token": "shared-token"},
        )
        old_preferences_response = await client.get(
            "/v1/notification-devices/old-install/preferences",
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert old_preferences_response.status_code == 404


async def test_updates_and_reads_notification_preferences() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "android", "push_token": "push-token"},
        )

        update_response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "enabled": True,
                "line_ids": ["Victoria", "central", "victoria"],
                "severity_threshold": "severe_delays",
                "notify_recoveries": False,
                "timezone": "Europe/London",
                "schedule_preset": "weekday_peak",
            },
        )
        read_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert update_response.status_code == 200
    assert read_response.status_code == 200
    assert read_response.json()["device_id"] == "install-123"
    assert read_response.json()["enabled"] is True
    assert read_response.json()["line_ids"] == ["victoria", "central"]
    assert read_response.json()["severity_threshold"] == "severe_delays"
    assert read_response.json()["notify_recoveries"] is False
    assert read_response.json()["timezone"] == "Europe/London"
    assert read_response.json()["schedule_preset"] == "weekday_peak"
    assert read_response.json()["custom_schedules"] == []


async def test_custom_preferences_require_schedule_windows() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "line_ids": ["victoria"],
                "schedule_preset": "custom",
                "custom_schedules": [],
            },
        )

    assert response.status_code == 422


async def test_custom_preferences_accept_schedule_windows() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "line_ids": ["victoria"],
                "schedule_preset": "custom",
                "custom_schedules": [
                    {
                        "days": ["mon", "tue", "wed", "thu", "fri"],
                        "start_time": "07:00",
                        "end_time": "09:30",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["custom_schedules"] == [
        {
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "start_time": "07:00:00",
            "end_time": "09:30:00",
        }
    ]


@pytest.mark.parametrize("schedule_preset", ["weekday_all_day", "weekends"])
async def test_preferences_accept_all_day_schedule_presets(schedule_preset: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "line_ids": ["victoria"],
                "schedule_preset": schedule_preset,
            },
        )

    assert response.status_code == 200
    assert response.json()["schedule_preset"] == schedule_preset
    assert response.json()["custom_schedules"] == []


@pytest.mark.parametrize(
    "schedule_preset",
    ["weekday_morning_peak", "weekday_evening_peak"],
)
async def test_preferences_reject_removed_peak_schedule_presets(
    schedule_preset: str,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "line_ids": ["victoria"],
                "schedule_preset": schedule_preset,
            },
        )

    assert response.status_code == 422


async def test_rejects_unsupported_line_ids() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={"line_ids": ["victoria", "imaginary"]},
        )

    assert response.status_code == 422


async def test_disables_notification_device_and_preferences() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={"line_ids": ["victoria"]},
        )

        disable_response = await client.post("/v1/notification-devices/install-123/disable")
        preferences_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert preferences_response.json()["enabled"] is False


async def test_deletes_notification_device() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        delete_response = await client.delete("/v1/notification-devices/install-123")
        read_response = await client.get("/v1/notification-devices/install-123/preferences")

    assert delete_response.status_code == 204
    assert read_response.status_code == 404


async def test_test_push_endpoint_is_gated_by_setting() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.post("/v1/notification-devices/install-123/test-push")

    assert response.status_code == 404


async def test_sends_test_push_to_known_ios_device() -> None:
    fake_sender = FakePushSender()
    app.dependency_overrides[get_settings] = lambda: Settings(apns_test_push_enabled=True)
    app.dependency_overrides[get_push_sender] = lambda: fake_sender

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.post("/v1/notification-devices/install-123/test-push")

    assert response.status_code == 200
    assert response.json() == {
        "device_id": "install-123",
        "status": "sent",
        "provider_message_id": "test-apns-id",
        "failure_reason": None,
    }
    assert fake_sender.delivery_device_ids == ["install-123"]
    assert fake_sender.event_types == ["test"]
