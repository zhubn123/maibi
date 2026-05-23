from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from core import AsrSessionConfig


@dataclass(frozen=True, slots=True)
class BootstrappedSession:
    provider: str
    websocket_url: str
    expires_at: datetime


class SessionBootstrapClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    async def create_tencent_session(self, config: AsrSessionConfig) -> BootstrappedSession:
        payload = {
            "provider": config.provider,
            "engine": config.engine,
            "hotwords": [hotword.text for hotword in config.hotwords],
            "client_session_id": config.client_session_id or "maibi-demo-session",
        }
        client_kwargs: dict[str, Any] = {"base_url": self.base_url, "timeout": 10.0}
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post("/v1/asr/session", json=payload)
            response.raise_for_status()
            data = response.json()
        return BootstrappedSession(
            provider=data["provider"],
            websocket_url=data["websocket_url"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
