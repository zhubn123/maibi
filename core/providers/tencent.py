from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import AsrEvent, AsrEventType, AsrProvider, AsrSession, AsrSessionConfig, Hotword

TENCENT_ASR_HOST = "asr.cloud.tencent.com"
TENCENT_ASR_PATH = "/asr/v2/{appid}"
TENCENT_ASR_SCHEME = "wss"
DEFAULT_URL_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class TencentAsrCredentials:
    appid: str
    secret_id: str
    secret_key: str

    def __post_init__(self) -> None:
        if not self.appid:
            raise ValueError("appid must not be empty")
        if not self.secret_id:
            raise ValueError("secret_id must not be empty")
        if not self.secret_key:
            raise ValueError("secret_key must not be empty")


@dataclass(frozen=True, slots=True)
class TencentAsrUrlBuilder:
    credentials: TencentAsrCredentials
    host: str = TENCENT_ASR_HOST
    scheme: str = TENCENT_ASR_SCHEME
    ttl_seconds: int = DEFAULT_URL_TTL_SECONDS

    def build_url(
        self,
        config: AsrSessionConfig,
        *,
        now: int | None = None,
        nonce: int | None = None,
    ) -> str:
        timestamp = int(time.time() if now is None else now)
        request_nonce = int(timestamp if nonce is None else nonce)
        path = TENCENT_ASR_PATH.format(appid=self.credentials.appid)
        params = self._query_params(
            config,
            timestamp=timestamp,
            nonce=request_nonce,
            voice_id=_resolve_voice_id(config, request_nonce),
        )
        signature = _sign_query(
            host=self.host,
            path=path,
            params=params,
            secret_key=self.credentials.secret_key,
        )
        params["signature"] = signature
        return urlunsplit((self.scheme, self.host, path, urlencode(params), ""))

    def _query_params(
        self,
        config: AsrSessionConfig,
        *,
        timestamp: int,
        nonce: int,
        voice_id: str,
    ) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "engine_model_type": config.engine,
            "expired": timestamp + self.ttl_seconds,
            "filter_modal": 1,
            "needvad": 1,
            "nonce": nonce,
            "secretid": self.credentials.secret_id,
            "timestamp": timestamp,
            "vad_silence_time": 1000,
            "voice_format": 1,
            "voice_id": voice_id,
        }
        hotword_list = format_hotword_list(config.hotwords)
        if hotword_list:
            params["hotword_list"] = hotword_list
        return params


class TencentWebSocketTransport(Protocol):
    async def send(self, data: bytes) -> None: ...
    async def recv(self) -> str: ...
    async def close(self) -> None: ...


class TencentWebSocketDialer(Protocol):
    async def connect(self, url: str) -> TencentWebSocketTransport: ...


@dataclass(slots=True)
class TencentAsrSession(AsrSession):
    transport: TencentWebSocketTransport

    async def send_audio(self, frame: bytes) -> None:
        await self.transport.send(frame)

    async def finish(self) -> None:
        await self.transport.send(json.dumps({"type": "end"}).encode("utf-8"))

    async def cancel(self) -> None:
        await self.transport.close()

    async def receive_event(self) -> AsrEvent:
        message = await self.transport.recv()
        return parse_asr_event(message)


@dataclass(frozen=True, slots=True)
class TencentAsrProvider(AsrProvider):
    url_builder: TencentAsrUrlBuilder
    dialer: TencentWebSocketDialer | None = None

    async def start_session(self, config: AsrSessionConfig) -> AsrSession:
        if self.dialer is None:
            raise RuntimeError("websocket dialer is not configured")
        url = self.build_session_url(config)
        transport = await self.dialer.connect(url)
        return TencentAsrSession(transport)

    def build_session_url(self, config: AsrSessionConfig, *, now: int | None = None) -> str:
        return self.url_builder.build_url(config, now=now)


@dataclass(frozen=True, slots=True)
class WebSocketsTencentTransport:
    websocket: object

    async def send(self, data: bytes) -> None:
        await self.websocket.send(data)  # type: ignore[attr-defined]

    async def recv(self) -> str:
        message = await self.websocket.recv()  # type: ignore[attr-defined]
        if isinstance(message, bytes):
            return message.decode("utf-8")
        return str(message)

    async def close(self) -> None:
        await self.websocket.close()  # type: ignore[attr-defined]


class WebSocketsTencentDialer:
    async def connect(self, url: str) -> TencentWebSocketTransport:
        import websockets

        websocket = await websockets.connect(url)
        return WebSocketsTencentTransport(websocket)


def format_hotword_list(hotwords: tuple[Hotword, ...]) -> str:
    return ",".join(f"{hotword.text}|{hotword.weight}" for hotword in hotwords)


def parse_asr_event(message: str) -> AsrEvent:
    payload = json.loads(message)
    code = int(payload.get("code", 0))
    if code != 0:
        return AsrEvent(
            type=AsrEventType.ERROR,
            text=str(payload.get("message", "")),
            error_code=str(code),
        )

    result = payload.get("result", {})
    text = str(result.get("voice_text_str", ""))
    final = bool(result.get("final", 0))
    stable = final or result.get("slice_type") == 2
    event_type = (
        AsrEventType.FINAL if final else AsrEventType.STABLE if stable else AsrEventType.PARTIAL
    )
    return AsrEvent(
        type=event_type,
        text=text,
        stable=stable,
        final=final,
    )


def redact_signed_url(url: str) -> str:
    split = urlsplit(url)
    redacted_params: list[tuple[str, str]] = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        if key.lower() in {"signature", "secretid", "hotword_list"}:
            redacted_params.append((key, "<redacted>"))
        else:
            redacted_params.append((key, value))
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            urlencode(redacted_params),
            split.fragment,
        )
    )


def _sign_query(
    *,
    host: str,
    path: str,
    params: dict[str, str | int],
    secret_key: str,
) -> str:
    sorted_query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    payload = f"{host}{path}?{sorted_query}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _resolve_voice_id(config: AsrSessionConfig, nonce: int) -> str:
    if config.client_session_id:
        return config.client_session_id
    return f"maibi-{nonce}-{uuid.uuid4().hex[:12]}"
