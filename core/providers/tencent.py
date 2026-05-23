from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import AsrSessionConfig, Hotword

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
        params = self._query_params(config, timestamp, request_nonce)
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
        timestamp: int,
        nonce: int,
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
        }
        hotword_list = format_hotword_list(config.hotwords)
        if hotword_list:
            params["hotword_list"] = hotword_list
        return params


def format_hotword_list(hotwords: tuple[Hotword, ...]) -> str:
    return ",".join(f"{hotword.text}|{hotword.weight}" for hotword in hotwords)


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
    sorted_query = urlencode(sorted(params.items()))
    payload = f"{host}{path}?{sorted_query}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")
