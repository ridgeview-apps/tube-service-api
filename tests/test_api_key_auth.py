import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import app

IOS_SECRET = "ios-secret-that-is-at-least-32-characters"
IOS_ROTATED_SECRET = "rotated-ios-secret-at-least-32-characters"
WIDGET_SECRET = "widget-secret-that-is-at-least-32-characters"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def configure_api_keys(
    value: dict[str, list[str]] | None,
    *,
    app_env: str = "production",
) -> None:
    settings = Settings(
        app_env=app_env,
        client_api_keys=value or {},
        _env_file=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings


def test_settings_parse_client_api_keys_from_json_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "CLIENT_API_KEYS",
        f'{{"ios":["{IOS_SECRET}"],"widget":["{WIDGET_SECRET}"]}}',
    )

    settings = Settings(_env_file=None)

    assert set(settings.client_api_keys) == {"ios", "widget"}
    assert settings.client_api_keys["ios"][0].get_secret_value() == IOS_SECRET


def test_settings_reject_short_client_api_keys() -> None:
    with pytest.raises(ValidationError):
        Settings(
            client_api_keys={"ios": ["too-short"]},
            _env_file=None,
        )


async def request_timeline(api_key: str | None = None):
    headers = {"X-API-Key": api_key} if api_key is not None else {}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(
            "/v1/line-status/timeline",
            params={"line_id": "victoria", "operational_date": "2999-01-01"},
            headers=headers,
        )


async def test_line_status_requires_configured_api_key() -> None:
    configure_api_keys(None)

    response = await request_timeline()

    assert response.status_code == 503
    assert response.json() == {"detail": "API authentication is not configured"}


async def test_line_status_allows_missing_api_key_in_development() -> None:
    configure_api_keys(None, app_env="development")

    response = await request_timeline()

    assert response.status_code == 422
    assert response.json() == {"detail": "Operational date cannot be in the future"}


async def test_health_remains_public_without_configured_api_key() -> None:
    configure_api_keys(None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_line_status_rejects_missing_api_key() -> None:
    configure_api_keys({"ios": [IOS_SECRET]})

    response = await request_timeline()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


async def test_line_status_rejects_invalid_api_key() -> None:
    configure_api_keys({"ios": [IOS_SECRET]})

    response = await request_timeline("ios.wrong-api-key")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


async def test_line_status_rejects_unknown_client() -> None:
    configure_api_keys({"ios": [IOS_SECRET]})

    response = await request_timeline(f"widget.{WIDGET_SECRET}")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


async def test_line_status_accepts_separate_client_keys() -> None:
    configure_api_keys(
        {
            "ios": [IOS_SECRET],
            "widget": [WIDGET_SECRET],
        }
    )

    ios_response = await request_timeline(f"ios.{IOS_SECRET}")
    widget_response = await request_timeline(f"widget.{WIDGET_SECRET}")

    assert ios_response.status_code == 422
    assert widget_response.status_code == 422


async def test_line_status_accepts_overlapping_keys_during_rotation() -> None:
    configure_api_keys({"ios": [IOS_ROTATED_SECRET, IOS_SECRET]})

    new_key_response = await request_timeline(f"ios.{IOS_ROTATED_SECRET}")
    old_key_response = await request_timeline(f"ios.{IOS_SECRET}")

    assert new_key_response.status_code == 422
    assert old_key_response.status_code == 422


async def test_line_status_rejects_removed_rotation_key() -> None:
    configure_api_keys({"ios": [IOS_ROTATED_SECRET]})

    response = await request_timeline(f"ios.{IOS_SECRET}")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}
