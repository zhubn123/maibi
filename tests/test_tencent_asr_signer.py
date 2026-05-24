import asyncio
import json
from urllib.parse import parse_qs, urlsplit

from core import AsrSessionConfig, Hotword
from core.providers.tencent import (
    TencentAsrProvider,
    TencentAsrSession,
    TencentAsrCredentials,
    TencentAsrUrlBuilder,
    WebSocketsTencentTransport,
    format_hotword_list,
    parse_asr_event,
    redact_signed_url,
)


def test_format_hotword_list_uses_tencent_weight_syntax() -> None:
    hotwords = (Hotword("麦笔"), Hotword("客户名称", weight=6))

    assert format_hotword_list(hotwords) == "麦笔|8,客户名称|6"


def test_tencent_url_builder_adds_expected_default_params() -> None:
    builder = TencentAsrUrlBuilder(
        TencentAsrCredentials(
            appid="123456",
            secret_id="secret-id",
            secret_key="secret-key",
        )
    )
    config = AsrSessionConfig(hotwords=(Hotword("麦笔"),))

    url = builder.build_url(config, now=1_700_000_000, nonce=42)
    split = urlsplit(url)
    params = parse_qs(split.query)

    assert split.scheme == "wss"
    assert split.netloc == "asr.cloud.tencent.com"
    assert split.path == "/asr/v2/123456"
    assert params["engine_model_type"] == ["16k_zh"]
    assert params["voice_format"] == ["1"]
    assert params["needvad"] == ["1"]
    assert params["vad_silence_time"] == ["1000"]
    assert params["filter_modal"] == ["1"]
    assert params["secretid"] == ["secret-id"]
    assert params["timestamp"] == ["1700000000"]
    assert params["expired"] == ["1700000300"]
    assert params["nonce"] == ["42"]
    assert params["voice_id"] == ["maibi-42-3c7d1d5168a0"] or params["voice_id"][0].startswith("maibi-42-")
    assert params["hotword_list"] == ["麦笔|8"]
    assert params["signature"]


def test_tencent_url_signature_is_deterministic_for_fixed_inputs() -> None:
    credentials = TencentAsrCredentials(
        appid="123456",
        secret_id="secret-id",
        secret_key="secret-key",
    )
    builder = TencentAsrUrlBuilder(credentials)
    config = AsrSessionConfig(client_session_id="session-1")

    assert builder.build_url(config, now=1_700_000_000, nonce=42) == builder.build_url(
        config,
        now=1_700_000_000,
        nonce=42,
    )
    assert "voice_id=session-1" in builder.build_url(config, now=1_700_000_000, nonce=42)


def test_redact_signed_url_hides_sensitive_query_values() -> None:
    builder = TencentAsrUrlBuilder(
        TencentAsrCredentials(
            appid="123456",
            secret_id="secret-id",
            secret_key="secret-key",
        )
    )
    url = builder.build_url(
        AsrSessionConfig(hotwords=(Hotword("客户名称"),)),
        now=1_700_000_000,
        nonce=42,
    )

    redacted = redact_signed_url(url)

    assert "secret-id" not in redacted
    assert "signature=" in redacted
    assert "hotword_list=" in redacted
    assert "%3Credacted%3E" in redacted
    assert "客户名称" not in redacted
    assert "secret-key" not in url


def test_parse_asr_event_maps_partial_stable_final_and_error() -> None:
    partial = parse_asr_event(
        json.dumps({"code": 0, "result": {"voice_text_str": "中间结果", "slice_type": 1, "final": 0, "index": 0}})
    )
    stable = parse_asr_event(
        json.dumps({"code": 0, "result": {"voice_text_str": "稳定结果", "slice_type": 2, "final": 0, "index": 0}})
    )
    final = parse_asr_event(
        json.dumps({"code": 0, "result": {"voice_text_str": "最终结果", "slice_type": 2, "final": 1, "index": 1}})
    )
    error = parse_asr_event(json.dumps({"code": 4001, "message": "bad request"}))

    assert partial.type.value == "partial"
    assert stable.type.value == "stable"
    assert final.type.value == "final"
    assert partial.segment_index == 0
    assert stable.segment_index == 0
    assert final.segment_index == 1
    assert error.type.value == "error"
    assert error.error_code == "4001"


def test_parse_asr_event_accepts_tencent_top_level_final_flag() -> None:
    event = parse_asr_event(
        json.dumps(
            {
                "code": 0,
                "final": 1,
                "result": {"voice_text_str": "最终结果", "slice_type": 2, "index": 0},
            }
        )
    )

    assert event.type.value == "final"
    assert event.final is True
    assert event.segment_index == 0


class _FakeTransport:
    def __init__(self, messages: list[str] | None = None) -> None:
        self.messages = list(messages or [])
        self.sent: list[bytes] = []
        self.closed = False

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return self.messages.pop(0)

    async def close(self) -> None:
        self.closed = True


class _FakeDialer:
    def __init__(self, transport: _FakeTransport) -> None:
        self.transport = transport
        self.urls: list[str] = []

    async def connect(self, url: str):
        self.urls.append(url)
        return self.transport


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.messages: list[str | bytes] = []
        self.closed = False

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def recv(self) -> str | bytes:
        return self.messages.pop(0)

    async def close(self) -> None:
        self.closed = True


def test_tencent_asr_session_sends_audio_and_finish_marker() -> None:
    async def scenario() -> None:
        transport = _FakeTransport(
            [json.dumps({"code": 0, "result": {"voice_text_str": "最终结果", "slice_type": 2, "final": 1}})]
        )
        session = TencentAsrSession(transport)

        await session.send_audio(b"\x00" * 6_400)
        await session.finish()
        event = await session.receive_event()
        await session.cancel()

        assert transport.sent[0] == b"\x00" * 6_400
        assert json.loads(transport.sent[1].decode("utf-8")) == {"type": "end"}
        assert event.final is True
        assert transport.closed is True

    asyncio.run(scenario())


def test_tencent_provider_builds_session_url_without_dialing() -> None:
    provider = TencentAsrProvider(
        TencentAsrUrlBuilder(
            TencentAsrCredentials(
                appid="123456",
                secret_id="secret-id",
                secret_key="secret-key",
            )
        )
    )

    url = provider.build_session_url(AsrSessionConfig(), now=1_700_000_000)

    assert url.startswith("wss://asr.cloud.tencent.com/asr/v2/123456?")


def test_tencent_provider_start_session_uses_dialer() -> None:
    transport = _FakeTransport()
    dialer = _FakeDialer(transport)
    provider = TencentAsrProvider(
        TencentAsrUrlBuilder(
            TencentAsrCredentials(
                appid="123456",
                secret_id="secret-id",
                secret_key="secret-key",
            )
        ),
        dialer=dialer,
    )

    async def scenario() -> None:
        session = await provider.start_session(AsrSessionConfig())
        assert isinstance(session, TencentAsrSession)
        assert len(dialer.urls) == 1
        assert dialer.urls[0].startswith("wss://asr.cloud.tencent.com/asr/v2/123456?")

    asyncio.run(scenario())


def test_websockets_transport_normalizes_text_and_bytes_messages() -> None:
    fake = _FakeWebSocket()
    fake.messages.extend([b'{"code":0}', '{"code":0}'])
    transport = WebSocketsTencentTransport(fake)

    async def scenario() -> None:
        await transport.send(b"\x01\x02")
        first = await transport.recv()
        second = await transport.recv()
        await transport.close()

        assert fake.sent == [b"\x01\x02"]
        assert first == '{"code":0}'
        assert second == '{"code":0}'
        assert fake.closed is True

    asyncio.run(scenario())
