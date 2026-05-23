from datetime import UTC, datetime

from fastapi.testclient import TestClient

from server.app import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_asr_session_returns_short_lived_session() -> None:
    client = TestClient(create_app())

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
    assert payload["websocket_url"].startswith("wss://")
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
