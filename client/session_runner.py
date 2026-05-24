from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass

from client.audio_capture import AudioCapturePipeline, AudioChunkSource, InMemoryAudioSource
from client.ui_state import (
    ClientUiState,
    apply_asr_event,
    begin_listening,
    begin_processing,
    reset_to_idle,
)
from core import AsrEvent, AsrSession, AsrSessionConfig
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
    on_event: Callable[[AsrEvent], None] | None = None,
) -> list[AsrEvent]:
    session = await provider.start_session(config)
    _sent_frames, events = await _run_session_tasks(
        session,
        _send_prepared_frames(session, frames),
        on_event=on_event,
    )
    return events


async def run_tencent_stream_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
    source: AudioChunkSource,
    *,
    on_event: Callable[[AsrEvent], None] | None = None,
    on_processing: Callable[[], None] | None = None,
) -> SessionRunResult:
    state = begin_listening()
    session = await provider.start_session(config)
    sent_frames, events = await _run_session_tasks(
        session,
        _send_source_frames(
            session,
            config,
            source,
            on_processing=on_processing,
        ),
        on_event=on_event,
    )

    state = begin_processing(state)
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
    on_event: Callable[[AsrEvent], None] | None = None,
    on_processing: Callable[[], None] | None = None,
) -> SessionRunResult:
    provider = TencentAsrProvider(
        url_builder=_StaticTencentUrlBuilder(websocket_url),
        dialer=dialer,
    )
    return await run_tencent_stream_session(
        provider,
        config,
        source,
        on_event=on_event,
        on_processing=on_processing,
    )


async def cancel_tencent_demo_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
) -> ClientUiState:
    session = await provider.start_session(config)
    await session.cancel()
    return reset_to_idle()


async def _run_session_tasks(
    session: AsrSession,
    sender: Coroutine[object, object, int],
    *,
    on_event: Callable[[AsrEvent], None] | None,
) -> tuple[int, list[AsrEvent]]:
    sender_task = asyncio.create_task(sender)
    receiver_task = asyncio.create_task(_receive_session_events(session, on_event))
    try:
        sent_frames, events = await asyncio.gather(sender_task, receiver_task)
    except Exception:
        sender_task.cancel()
        receiver_task.cancel()
        await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
        try:
            await session.cancel()
        except Exception:
            pass
        raise
    return sent_frames, events


async def _send_prepared_frames(session: AsrSession, frames: Iterable[bytes]) -> int:
    sent_frames = 0
    for frame in frames:
        await session.send_audio(frame)
        sent_frames += 1
    await session.finish()
    return sent_frames


async def _send_source_frames(
    session: AsrSession,
    config: AsrSessionConfig,
    source: AudioChunkSource,
    *,
    on_processing: Callable[[], None] | None,
) -> int:
    loop = asyncio.get_running_loop()
    sent_frames = 0

    def capture_and_send() -> None:
        nonlocal sent_frames
        pipeline = AudioCapturePipeline(
            source=source,
            audio_format=config.audio_format,
            frame_duration_ms=config.frame_duration_ms,
        )
        for frame in pipeline.frames():
            future = asyncio.run_coroutine_threadsafe(session.send_audio(frame.data), loop)
            future.result()
            sent_frames += 1

    await asyncio.to_thread(capture_and_send)
    if on_processing is not None:
        on_processing()
    await session.finish()
    return sent_frames


async def _receive_session_events(
    session: AsrSession,
    on_event: Callable[[AsrEvent], None] | None,
) -> list[AsrEvent]:
    events: list[AsrEvent] = []
    if not hasattr(session, "receive_event"):
        return events

    while True:
        event = await session.receive_event()  # type: ignore[attr-defined]
        events.append(event)
        if on_event is not None:
            on_event(event)
        if event.final or event.type.value == "error":
            break
    return events
