import asyncio
import json

from client.audio_capture import InMemoryAudioSource
from client.session_runner import (
    cancel_tencent_demo_session,
    run_tencent_demo_session,
    run_tencent_stream_session,
)
from core import AsrSessionConfig, Hotword
from core.providers.tencent import (
    TencentAsrCredentials,
    TencentAsrProvider,
    TencentAsrUrlBuilder,
)


class _FakeTransport:
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
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


def _provider_with_transport(messages: list[str]) -> tuple[TencentAsrProvider, _FakeTransport, _FakeDialer]:
    transport = _FakeTransport(messages)
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
    return provider, transport, dialer


def test_run_tencent_demo_session_sends_frames_and_applies_final_event() -> None:
    provider, transport, dialer = _provider_with_transport(
        [json.dumps({"code": 0, "result": {"voice_text_str": "最终文本", "slice_type": 2, "final": 1}})]
    )
    config = AsrSessionConfig(hotwords=(Hotword("麦笔"),))
    frame = b"\x00" * config.frame_size_bytes

    result = asyncio.run(run_tencent_demo_session(provider, config, [frame, frame]))

    assert len(dialer.urls) == 1
    assert result.sent_frames == 2
    assert transport.sent[0] == frame
    assert transport.sent[1] == frame
    assert json.loads(transport.sent[2].decode("utf-8")) == {"type": "end"}
    assert result.final_state.final_text == "最终文本"
    assert result.final_state.mode.value == "final"


def test_cancel_tencent_demo_session_closes_transport() -> None:
    provider, transport, _dialer = _provider_with_transport([])

    state = asyncio.run(cancel_tencent_demo_session(provider, AsrSessionConfig()))

    assert state.mode.value == "idle"
    assert transport.closed is True


def test_run_tencent_stream_session_accepts_audio_source_protocol() -> None:
    provider, transport, _dialer = _provider_with_transport(
        [json.dumps({"code": 0, "result": {"voice_text_str": "稳定结果", "slice_type": 2, "final": 1}})]
    )
    config = AsrSessionConfig()
    source = InMemoryAudioSource.from_chunks([b"\x00" * config.frame_size_bytes])

    result = asyncio.run(run_tencent_stream_session(provider, config, source))

    assert result.sent_frames == 1
    assert result.final_state.final_text == "稳定结果"
    assert transport.sent[0] == b"\x00" * config.frame_size_bytes
