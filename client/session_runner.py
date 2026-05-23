from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
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
from core.providers.tencent import TencentAsrProvider


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
    source: AudioChunkSource,
) -> AsyncIterator[AsrEvent]:
    pipeline = AudioCapturePipeline(
        source=source,
        audio_format=config.audio_format,
        frame_duration_ms=config.frame_duration_ms,
    )
    session = await provider.start_session(config)

    for frame in pipeline.frames():
        await session.send_audio(frame.data)

    await session.finish()

    if hasattr(session, "receive_event"):
        while True:
            event = await session.receive_event()  # type: ignore[attr-defined]
            yield event
            if event.final or event.type.value == "error":
                break


async def run_tencent_stream_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
    source: AudioChunkSource,
) -> SessionRunResult:
    state = begin_listening()
    pipeline = AudioCapturePipeline(
        source=source,
        audio_format=config.audio_format,
        frame_duration_ms=config.frame_duration_ms,
    )
    events: list[AsrEvent] = []
    sent_frames = sum(1 for _ in pipeline.frames())
    replay_source = InMemoryAudioSource.from_chunks(
        frame.data
        for frame in AudioCapturePipeline(
            source=source,
            audio_format=config.audio_format,
            frame_duration_ms=config.frame_duration_ms,
        ).frames()
    )

    state = begin_processing(state)
    async for event in stream_tencent_session_events(provider, config, replay_source):
        events.append(event)
        state = apply_asr_event(state, event)

    return SessionRunResult(final_state=state, events=events, sent_frames=sent_frames)


async def cancel_tencent_demo_session(
    provider: TencentAsrProvider,
    config: AsrSessionConfig,
) -> ClientUiState:
    session = await provider.start_session(config)
    await session.cancel()
    return reset_to_idle()
