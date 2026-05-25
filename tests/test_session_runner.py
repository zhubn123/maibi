import asyncio
import json
import threading
from collections.abc import Iterator

from client.audio_capture import InMemoryAudioSource
from client.session_runner import (
    cancel_tencent_demo_session,
    run_bootstrapped_tencent_stream_session,
    run_tencent_demo_session,
    run_tencent_stream_session,
)
from core import AsrSessionConfig, Hotword
from core.providers.tencent import (
    TencentAsrCredentials,
    TencentAsrProvider,
    TencentAsrUrlBuilder,
    WebSocketsTencentTransport,
)


class _FakeTransport:
    def __init__(self, messages: list[str], events: list[str] | None = None) -> None:
        self.messages = list(messages)
        self.events = events
        self.sent: list[bytes] = []
        self.closed = False

    async def send(self, data: bytes) -> None:
        if self.events is not None:
            self.events.append("send")
        self.sent.append(data)

    async def recv(self) -> str:
        return self.messages.pop(0)

    async def close(self) -> None:
        self.closed = True


class _FakeDialer:
    def __init__(self, transport: _FakeTransport, events: list[str] | None = None) -> None:
        self.transport = transport
        self.events = events
        self.urls: list[str] = []

    async def connect(self, url: str):
        if self.events is not None:
            self.events.append("connect")
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


class _TracingAudioSource:
    def __init__(self, events: list[str], chunks: list[bytes]) -> None:
        self.events = events
        self._chunks = chunks

    def chunks(self) -> Iterator[bytes]:
        self.events.append("source_start")
        for chunk in self._chunks:
            self.events.append("source_chunk")
            yield chunk
        self.events.append("source_done")


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


def test_run_bootstrapped_tencent_stream_session_uses_supplied_url() -> None:
    provider, transport, dialer = _provider_with_transport(
        [json.dumps({"code": 0, "result": {"voice_text_str": "最终文本", "slice_type": 2, "final": 1}})]
    )
    source = InMemoryAudioSource.from_chunks([b"\x00" * AsrSessionConfig().frame_size_bytes])
    result = asyncio.run(
        run_bootstrapped_tencent_stream_session(
            websocket_url="wss://bootstrap.example/session",
            config=AsrSessionConfig(),
            source=source,
            dialer=dialer,
        )
    )

    assert result.final_state.final_text == "最终文本"
    assert dialer.urls == ["wss://bootstrap.example/session"]


def test_stream_session_emits_events_in_partial_stable_final_order() -> None:
    provider, transport, _dialer = _provider_with_transport(
        [
            json.dumps({"code": 0, "result": {"voice_text_str": "中间结果", "slice_type": 1, "final": 0}}),
            json.dumps({"code": 0, "result": {"voice_text_str": "稳定结果", "slice_type": 2, "final": 0}}),
            json.dumps({"code": 0, "result": {"voice_text_str": "最终结果", "slice_type": 2, "final": 1}}),
        ]
    )
    config = AsrSessionConfig()
    frame = b"\x00" * config.frame_size_bytes
    seen: list[str] = []

    result = asyncio.run(
        run_tencent_stream_session(
            provider,
            config,
            InMemoryAudioSource.from_chunks([frame, frame]),
            on_event=lambda event: seen.append(event.type.value),
        )
    )

    assert seen == ["partial", "stable", "final"]
    assert result.final_state.final_text == "最终结果"
    assert transport.sent[0] == frame


def test_stream_session_connects_before_consuming_audio_source() -> None:
    events: list[str] = []
    transport = _FakeTransport(
        [json.dumps({"code": 0, "result": {"voice_text_str": "最终结果", "slice_type": 2, "final": 1}})],
        events,
    )
    dialer = _FakeDialer(transport, events)
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
    config = AsrSessionConfig()
    source = _TracingAudioSource(events, [b"\x00" * config.frame_size_bytes])
    processing_events: list[str] = []

    result = asyncio.run(
        run_tencent_stream_session(
            provider,
            config,
            source,
            on_processing=lambda: processing_events.append("processing"),
        )
    )

    assert result.sent_frames == 1
    assert events[:2] == ["connect", "source_start"]
    assert events.index("send") < events.index("source_done")
    assert events.index("source_done") < len(events)
    assert processing_events == ["processing"]


def test_stream_session_cancel_closes_transport_without_finish_marker() -> None:
    class _CancelAfterChunkSource:
        def __init__(self, cancel_event: threading.Event, frame: bytes) -> None:
            self.cancel_event = cancel_event
            self.frame = frame

        def chunks(self) -> Iterator[bytes]:
            yield self.frame
            self.cancel_event.set()
            yield self.frame

    cancel_event = threading.Event()
    config = AsrSessionConfig()
    transport = _FakeTransport(
        [json.dumps({"code": 0, "result": {"voice_text_str": "不应等待", "slice_type": 2, "final": 1}})]
    )
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

    result = asyncio.run(
        run_tencent_stream_session(
            provider,
            config,
            _CancelAfterChunkSource(cancel_event, b"\x00" * config.frame_size_bytes),
            cancel_event=cancel_event,
        )
    )

    assert result.sent_frames == 1
    assert result.events == []
    assert transport.closed is True
    assert all(json.loads(data.decode("utf-8")) != {"type": "end"} for data in transport.sent if data.startswith(b"{"))


def test_stream_session_treats_clean_close_after_stable_event_as_final() -> None:
    class ConnectionClosedOK(Exception):
        code = 1000
        reason = "normal"

    class _ClosingWebSocket:
        def __init__(self, messages: list[str]) -> None:
            self.messages = list(messages)
            self.sent: list[bytes] = []
            self.closed = False

        async def send(self, data: bytes) -> None:
            self.sent.append(data)

        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            raise ConnectionClosedOK()

        async def close(self) -> None:
            self.closed = True

    config = AsrSessionConfig()
    websocket = _ClosingWebSocket(
        [json.dumps({"code": 0, "result": {"voice_text_str": "稳定结果", "slice_type": 2, "final": 0, "index": 0}})]
    )
    transport = WebSocketsTencentTransport(websocket)
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
    seen: list[str] = []

    result = asyncio.run(
        run_tencent_stream_session(
            provider,
            config,
            InMemoryAudioSource.from_chunks([b"\x00" * config.frame_size_bytes]),
            on_event=lambda event: seen.append(event.type.value),
        )
    )

    assert seen == ["stable", "final"]
    assert result.final_state.final_text == "稳定结果"
    assert result.final_state.mode.value == "final"
    assert json.loads(websocket.sent[-1].decode("utf-8")) == {"type": "end"}


def test_stream_session_keeps_stable_text_when_provider_reports_late_error() -> None:
    provider, _transport, _dialer = _provider_with_transport(
        [
            json.dumps({"code": 0, "result": {"voice_text_str": "稳定结果", "slice_type": 2, "final": 0, "index": 0}}),
            json.dumps({"code": 4008, "message": "backend timeout"}),
        ]
    )
    config = AsrSessionConfig()
    seen: list[str] = []

    result = asyncio.run(
        run_tencent_stream_session(
            provider,
            config,
            InMemoryAudioSource.from_chunks([b"\x00" * config.frame_size_bytes]),
            on_event=lambda event: seen.append(event.type.value),
        )
    )

    assert seen == ["stable", "error"]
    assert result.final_state.mode.value == "final"
    assert result.final_state.final_text == "稳定结果"
