from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.app import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_asr_session_returns_short_lived_session() -> None:
    client = TestClient(create_app())
    with patch(
        "server.app._load_tencent_service_config",
        return_value=__import__("core").TencentAsrServiceConfig(
            appid="123456",
            secret_id="secret-id",
            secret_key="secret-key",
        ),
    ):
        response = client.post(
            "/v1/asr/session",
            json={
                "provider": "tencent",
                "engine": "16k_zh",
                "hotwords": ["麦笔"],
                "client_session_id": "session-1",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "tencent"
    assert payload["websocket_url"].startswith("wss://asr.cloud.tencent.com/asr/v2/123456?")
    assert datetime.fromisoformat(payload["expires_at"]) > datetime.now(UTC)


def test_create_asr_session_rejects_unsupported_provider() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/asr/session",
        json={
            "provider": "unknown",
            "engine": "16k_zh",
            "hotwords": [],
            "client_session_id": "session-1",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported provider"


def test_create_asr_session_rejects_invalid_hotword() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/asr/session",
        json={
            "provider": "tencent",
            "engine": "16k_zh",
            "hotwords": ["客户 名称"],
            "client_session_id": "session-1",
        },
    )

    assert response.status_code == 422
    assert "whitespace" in response.json()["detail"]


def test_create_asr_session_requires_configured_credentials() -> None:
    client = TestClient(create_app())
    with patch(
        "server.app._load_tencent_service_config",
        side_effect=__import__("fastapi").HTTPException(
            status_code=503,
            detail="tencent_asr_credentials_not_configured",
        ),
    ):
        response = client.post(
            "/v1/asr/session",
            json={
                "provider": "tencent",
                "engine": "16k_zh",
                "hotwords": [],
                "client_session_id": "session-1",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "tencent_asr_credentials_not_configured"


def test_tencent_service_config_uses_default_ttl() -> None:
    from core import TencentAsrServiceConfig

    config = TencentAsrServiceConfig.from_dict(
        {
            "tencent_asr": {
                "appid": "123456",
                "secret_id": "secret-id",
                "secret_key": "secret-key",
            }
        },
    )

    assert config.appid == "123456"
    assert config.secret_id == "secret-id"
    assert config.secret_key == "secret-key"
    assert config.session_ttl_seconds == 300
