import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes.notifications import get_push_sender
from app.api.security import require_api_key
from app.config import Settings, get_settings
from app.database import Base, get_session
from app.main import app
from app.notifications.models import NotificationDevice
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
    assert second_response.json()["app_variant"] == "production"
    for field in ("created_at", "updated_at", "last_seen_at"):
        assert second_response.json()[field].endswith("Z")
        assert "." not in second_response.json()[field]


async def test_reregistering_disabled_device_preserves_enabled_state() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "first-token"},
        )
        disable_response = await client.post("/v1/notification-devices/install-123/disable")
        reregister_response = await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "rotated-token"},
        )

    assert disable_response.status_code == 200
    assert reregister_response.status_code == 200
    assert reregister_response.json()["enabled"] is False


def test_notification_schedule_time_openapi_docs() -> None:
    schemas = app.openapi()["components"]["schemas"]
    input_properties = schemas["NotificationScheduleWindow-Input"]["properties"]
    output_properties = schemas["NotificationScheduleWindow-Output"]["properties"]

    assert input_properties["start_time"] == {
        "type": "string",
        "format": "time",
        "title": "Start Time",
        "description": (
            "A local time. Send HH:mm; seconds are accepted and discarded. "
            "Always returned in HH:mm format."
        ),
    }
    assert output_properties["start_time"] == {
        "type": "string",
        "pattern": r"^\d{2}:\d{2}$",
        "title": "Start Time",
        "description": (
            "A local time. Send HH:mm; seconds are accepted and discarded. "
            "Always returned in HH:mm format."
        ),
        "examples": ["06:30"],
    }


def test_notification_preferences_patch_openapi_examples() -> None:
    request_body = app.openapi()["paths"]["/v1/notification-devices/{device_id}/preferences"][
        "patch"
    ]["requestBody"]
    merge_patch_content = request_body["content"]["application/merge-patch+json"]

    assert merge_patch_content["examples"]["update-and-remove"]["value"] == {
        "lines": {"victoria": {"enabled": False}, "central": None}
    }
    assert merge_patch_content["examples"]["add-line"]["value"]["lines"]["victoria"]["schedules"][
        0
    ]["windows"] == [{"start_time": "06:30", "end_time": "09:30"}]


async def test_registers_notification_device_app_variant() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.put(
            "/v1/notification-devices/install-123",
            json={
                "platform": "ios",
                "push_token": "push-token",
                "app_variant": "beta",
            },
        )

    assert response.status_code == 200
    assert response.json()["app_variant"] == "beta"


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
                "timezone": "Europe/London",
                "lines": [
                    {
                        "line_id": "Victoria",
                        "severity_threshold": "severe_delays",
                        "notify_recoveries": False,
                        "schedules": [
                            {
                                "days": ["mon", "tue", "wed", "thu", "fri"],
                                "windows": [
                                    {"start_time": "06:30", "end_time": "09:30"},
                                    {"start_time": "16:00", "end_time": "19:00"},
                                ],
                            }
                        ],
                    },
                    {
                        "line_id": "central",
                        "enabled": False,
                        "schedules": [
                            {
                                "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                                "all_day": True,
                            }
                        ],
                    },
                ],
            },
        )
        read_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert update_response.status_code == 200
    assert read_response.status_code == 200
    assert read_response.json()["device_id"] == "install-123"
    assert read_response.json()["timezone"] == "Europe/London"
    assert read_response.json()["lines"] == [
        {
            "enabled": False,
            "line_id": "central",
            "severity_threshold": "minor_delays",
            "notify_recoveries": True,
            "schedules": [
                {
                    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                    "all_day": True,
                    "windows": [],
                }
            ],
        },
        {
            "enabled": True,
            "line_id": "victoria",
            "severity_threshold": "severe_delays",
            "notify_recoveries": False,
            "schedules": [
                {
                    "days": ["mon", "tue", "wed", "thu", "fri"],
                    "all_day": False,
                    "windows": [
                        {"start_time": "06:30", "end_time": "09:30"},
                        {"start_time": "16:00", "end_time": "19:00"},
                    ],
                }
            ],
        },
    ]


async def test_preferences_require_explicit_schedules() -> None:
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
                "lines": [
                    {
                        "line_id": "victoria",
                    }
                ],
            },
        )

    assert response.status_code == 422


async def test_preferences_accept_multiple_explicit_schedule_rules() -> None:
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
                "lines": [
                    {
                        "line_id": "victoria",
                        "schedules": [
                            {
                                "days": ["mon", "tue", "wed", "thu", "fri"],
                                "windows": [{"start_time": "07:00:45", "end_time": "09:30:59"}],
                            },
                            {"days": ["sat"], "all_day": True},
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["lines"][0]["schedules"] == [
        {
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "all_day": False,
            "windows": [{"start_time": "07:00", "end_time": "09:30"}],
        },
        {"days": ["sat"], "all_day": True, "windows": []},
    ]


async def test_preferences_rejects_all_day_schedules_with_windows() -> None:
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
                "lines": [
                    {
                        "line_id": "victoria",
                        "schedules": [
                            {
                                "days": ["sat"],
                                "all_day": True,
                                "windows": [{"start_time": "07:00", "end_time": "09:30"}],
                            }
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 422


async def test_preferences_rejects_timed_schedules_without_windows() -> None:
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
                "lines": [
                    {
                        "line_id": "victoria",
                        "schedules": [{"days": ["mon"]}],
                    }
                ],
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
            json={"lines": [{"line_id": "victoria"}, {"line_id": "imaginary"}]},
        )

    assert response.status_code == 422


async def test_rejects_duplicate_normalized_line_ids() -> None:
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
            json={"lines": [{"line_id": "Victoria"}, {"line_id": "victoria"}]},
        )

    assert response.status_code == 422


async def test_updating_preferences_replaces_omitted_lines() -> None:
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
            json={
                "lines": [
                    {"line_id": "victoria", "schedules": [{"days": ["mon"], "all_day": True}]},
                    {"line_id": "central", "schedules": [{"days": ["mon"], "all_day": True}]},
                ]
            },
        )
        update_response = await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "lines": [{"line_id": "central", "schedules": [{"days": ["mon"], "all_day": True}]}]
            },
        )
        read_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert update_response.status_code == 200
    assert [line["line_id"] for line in read_response.json()["lines"]] == ["central"]


async def test_patch_preferences_updates_only_the_targeted_line() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "lines": [
                    {
                        "line_id": "victoria",
                        "enabled": True,
                        "schedules": [{"days": ["mon"], "all_day": True}],
                    },
                    {
                        "line_id": "central",
                        "enabled": True,
                        "schedules": [{"days": ["tue"], "all_day": True}],
                    },
                ]
            },
        )
        response = await client.patch(
            "/v1/notification-devices/install-123/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={"lines": {"victoria": {"enabled": False}}},
        )

    assert response.status_code == 200
    lines = {line["line_id"]: line for line in response.json()["lines"]}
    assert lines["victoria"]["enabled"] is False
    assert lines["victoria"]["schedules"] == [{"days": ["mon"], "all_day": True, "windows": []}]
    assert lines["central"]["enabled"] is True
    assert lines["central"]["schedules"] == [{"days": ["tue"], "all_day": True, "windows": []}]


async def test_patch_preferences_removes_a_line_with_null() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={
                "lines": [
                    {"line_id": "victoria", "schedules": [{"days": ["mon"], "all_day": True}]},
                    {"line_id": "central", "schedules": [{"days": ["mon"], "all_day": True}]},
                ]
            },
        )
        response = await client.patch(
            "/v1/notification-devices/install-123/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={"lines": {"central": None}},
        )

    assert response.status_code == 200
    assert [line["line_id"] for line in response.json()["lines"]] == ["victoria"]


async def test_patch_preferences_adds_a_fully_specified_line() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.patch(
            "/v1/notification-devices/install-123/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={
                "lines": {
                    "victoria": {
                        "enabled": False,
                        "severity_threshold": "severe_delays",
                        "notify_recoveries": False,
                        "schedules": [{"days": ["sat"], "all_day": True}],
                    }
                }
            },
        )

    assert response.status_code == 200
    assert response.json()["lines"][0]["line_id"] == "victoria"
    assert response.json()["lines"][0]["severity_threshold"] == "severe_delays"


async def test_patch_preferences_rejects_partially_specified_new_line() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.patch(
            "/v1/notification-devices/install-123/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={"lines": {"victoria": {"enabled": False}}},
        )

    assert response.status_code == 422


async def test_patch_preferences_rejects_unknown_line_id() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        response = await client.patch(
            "/v1/notification-devices/install-123/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={"lines": {"imaginary": None}},
        )

    assert response.status_code == 422


async def test_patch_preferences_returns_not_found_for_unknown_device() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/v1/notification-devices/unknown/preferences",
            headers={"Content-Type": "application/merge-patch+json"},
            json={"lines": {}},
        )

    assert response.status_code == 404


async def test_disables_notification_device_without_changing_line_preferences() -> None:
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
            json={
                "lines": [
                    {"line_id": "victoria", "schedules": [{"days": ["mon"], "all_day": True}]}
                ]
            },
        )

        disable_response = await client.post("/v1/notification-devices/install-123/disable")
        preferences_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert preferences_response.json()["lines"][0]["enabled"] is True


async def test_enables_notification_device_without_changing_line_preferences() -> None:
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
            json={
                "lines": [
                    {
                        "line_id": "victoria",
                        "enabled": False,
                        "schedules": [{"days": ["mon"], "all_day": True}],
                    }
                ]
            },
        )
        await client.post("/v1/notification-devices/install-123/disable")

        enable_response = await client.post("/v1/notification-devices/install-123/enable")
        preferences_response = await client.get(
            "/v1/notification-devices/install-123/preferences",
        )

    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True
    assert preferences_response.json()["lines"][0]["enabled"] is False


async def test_updating_preferences_does_not_reenable_disabled_device() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.put(
            "/v1/notification-devices/install-123",
            json={"platform": "ios", "push_token": "push-token"},
        )
        await client.post("/v1/notification-devices/install-123/disable")
        await client.put(
            "/v1/notification-devices/install-123/preferences",
            json={"lines": [{"line_id": "victoria", "enabled": True}]},
        )

    async with db_session_factory() as session:
        device = await session.scalar(
            select(NotificationDevice).where(NotificationDevice.device_id == "install-123")
        )

    assert device is not None
    assert device.enabled is False


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
    app.dependency_overrides[get_settings] = lambda: Settings(apns_test_push_enabled=False)

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
