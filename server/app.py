from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core import AsrSessionConfig, Hotword

SESSION_TTL_SECONDS = 300
SUPPORTED_PROVIDERS = {"tencent"}


class AsrSessionRequest(BaseModel):
    provider: str = "tencent"
    engine: str = "16k_zh"
    hotwords: list[str] = Field(default_factory=list)
    client_session_id: str


class AsrSessionResponse(BaseModel):
    provider: str
    websocket_url: str
    expires_at: datetime


def create_app() -> FastAPI:
    app = FastAPI(title="Maibi Signing Service", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/asr/session", response_model=AsrSessionResponse)
    def create_asr_session(request: AsrSessionRequest) -> AsrSessionResponse:
        if request.provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail="unsupported provider")

        try:
            hotwords = tuple(Hotword(text) for text in request.hotwords)
            config = AsrSessionConfig(
                provider=request.provider,
                engine=request.engine,
                hotwords=hotwords,
                client_session_id=request.client_session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        expires_at = datetime.now(UTC) + timedelta(seconds=SESSION_TTL_SECONDS)
        return AsrSessionResponse(
            provider=config.provider,
            websocket_url=_placeholder_websocket_url(config),
            expires_at=expires_at,
        )

    return app


def _placeholder_websocket_url(config: AsrSessionConfig) -> str:
    return (
        "wss://asr.invalid.example/session"
        f"?provider={config.provider}&engine={config.engine}"
    )


app = create_app()
