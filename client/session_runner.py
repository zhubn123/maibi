from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from client.audio_capture import AudioCapturePipeline, AudioChunkSource, InMemoryAudioSource
from client.ui_state import (
    ClientUiState,
    apply_asr_event,
    begin_listening,
    begin_processing,
    reset_to_idle,
)
from core import AsrEvent, AsrSessionConfig
from core.providers.tencent import TencentAsrProvider, TencentWebSocketDialer


@dataclass(slots=True)
class SessionRunResult:
    final_state: ClientUiState
    events: list[AsrEvent]
    sent_frames: int


async def run_tencent_demo_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
    pcm_chunks: Iterable[bytes],
) -> SessionRunResult:
    return await run_tencent_stream_session(
        provider=provider,
        config=config,
        source=InMemoryAudioSource.from_chunks(pcm_chunks),
    )


async def stream_tencent_session_events(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
    frames: list[bytes],
) -> list[AsrEvent]:
    session = await provider.start_session(config)
    events: list[AsrEvent] = []

    for frame in frames:
        await session.send_audio(frame)

    await session.finish()

    if hasattr(session, "receive_event"):
        while True:
            event = await session.receive_event()  # type: ignore[attr-defined]
            events.append(event)
            if event.final or event.type.value == "error":
                break
    return events


async def run_tencent_stream_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
    source: AudioChunkSource,
) -> SessionRunResult:
    state = begin_listening()
    frames = [
        frame.data
        for frame in AudioCapturePipeline(
            source=source,
            audio_format=config.audio_format,
            frame_duration_ms=config.frame_duration_ms,
        ).frames()
    ]
    sent_frames = len(frames)

    state = begin_processing(state)
    events = await stream_tencent_session_events(provider, config, frames)
    for event in events:
        state = apply_asr_event(state, event)

    return SessionRunResult(final_state=state, events=events, sent_frames=sent_frames)


class _StaticTencentUrlBuilder:
    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url

    def build_url(self, _config: AsrSessionConfig, *, now: int | None = None) -> str:
        return self.websocket_url


async def run_bootstrapped_tencent_stream_session(
    *,
    websocket_url: str,
    config: AsrSessionConfig,
    source: AudioChunkSource,
    dialer: TencentWebSocketDialer,
) -> SessionRunResult:
    provider = TencentAsrProvider(
        url_builder=_StaticTencentUrlBuilder(websocket_url),
        dialer=dialer,
    )
    return await run_tencent_stream_session(provider, config, source)


async def cancel_tencent_demo_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
) -> ClientUiState:
    session = await provider.start_session(config)
    await session.cancel()
    return reset_to_idle()
