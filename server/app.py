from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core import AsrSessionConfig, Hotword, TencentAsrServiceConfig
from core.providers.tencent import TencentAsrCredentials, TencentAsrUrlBuilder

SESSION_TTL_SECONDS = 300
SUPPORTED_PROVIDERS = {"tencent"}
LOCAL_CONFIG_PATH = Path("server/config.local.json")


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

        service_config = _load_tencent_service_config()
        credentials = TencentAsrCredentials(
            appid=service_config.appid,
            secret_id=service_config.secret_id,
            secret_key=service_config.secret_key,
        )
        builder = TencentAsrUrlBuilder(credentials, ttl_seconds=service_config.session_ttl_seconds)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=service_config.session_ttl_seconds)
        return AsrSessionResponse(
            provider=config.provider,
            websocket_url=builder.build_url(config),
            expires_at=expires_at,
        )

    return app


def _load_tencent_service_config() -> TencentAsrServiceConfig:
    try:
        return TencentAsrServiceConfig.from_file(LOCAL_CONFIG_PATH)
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="tencent_asr_credentials_not_configured",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="tencent_asr_credentials_not_configured",
        )


app = create_app()
