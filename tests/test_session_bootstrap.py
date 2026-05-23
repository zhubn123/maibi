from datetime import datetime

import httpx
import pytest

from client.session_bootstrap import SessionBootstrapClient
from core import AsrSessionConfig, Hotword


@pytest.mark.anyio
async def test_session_bootstrap_posts_config_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "provider": "tencent",
                "websocket_url": "wss://asr.cloud.tencent.com/asr/v2/123456?signature=x",
                "expires_at": "2026-05-23T12:00:00+08:00",
            },
        )

    transport = httpx.MockTransport(handler)
    config = AsrSessionConfig(hotwords=(Hotword("麦笔"),), client_session_id="session-1")

    client = SessionBootstrapClient("http://bootstrap.example", transport=transport)
    result = await client.create_tencent_session(config)

    assert captured["url"] == "http://bootstrap.example/v1/asr/session"
    assert '"provider":"tencent"' in str(captured["json"])
    assert '"engine":"16k_zh"' in str(captured["json"])
    assert '"hotwords":["麦笔"]' in str(captured["json"])
    assert result.provider == "tencent"
    assert result.websocket_url.startswith("wss://")
    assert isinstance(result.expires_at, datetime)
