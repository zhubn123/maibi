from __future__ import annotations

import asyncio
import logging
import threading
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
from core import AsrEvent, AsrEventType, AsrSession, AsrSessionConfig
from core.providers.tencent import TencentAsrProvider, TencentAsrStreamClosed, TencentWebSocketDialer

LOGGER = logging.getLogger(__name__)


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
    on_capture_ready: Callable[[], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> SessionRunResult:
    state = begin_listening()
    LOGGER.info("asr stream starting provider=%s frame_duration_ms=%s", config.provider, config.frame_duration_ms)
    session = await provider.start_session(config)
    sent_frames, events = await _run_session_tasks(
        session,
        _send_source_frames(
            session,
            config,
            source,
            on_processing=on_processing,
            on_capture_ready=on_capture_ready,
            cancel_event=cancel_event,
        ),
        on_event=on_event,
        cancel_event=cancel_event,
    )

    state = begin_processing(state)
    for event in events:
        state = apply_asr_event(state, event)

    LOGGER.info("asr stream completed sent_frames=%s events=%s final_mode=%s", sent_frames, len(events), state.mode.value)
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
    on_capture_ready: Callable[[], None] | None = None,
    cancel_event: threading.Event | None = None,
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
        on_capture_ready=on_capture_ready,
        cancel_event=cancel_event,
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
    cancel_event: threading.Event | None = None,
) -> tuple[int, list[AsrEvent]]:
    sender_task = asyncio.create_task(sender)
    receiver_task = asyncio.create_task(
        _receive_session_events(
            session,
            on_event,
            cancel_event=cancel_event,
        )
    )
    cancel_task = (
        asyncio.create_task(_watch_cancel_event(session, cancel_event))
        if cancel_event is not None
        else None
    )
    try:
        tasks = {sender_task, receiver_task}
        if cancel_task is not None:
            tasks.add(cancel_task)
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if cancel_event is not None and cancel_event.is_set():
            LOGGER.info("asr stream cancellation observed; closing session")
            try:
                await session.cancel()
            except Exception:
                pass
            sender_task.cancel()
            receiver_task.cancel()
            pending_tasks = [sender_task, receiver_task]
            if cancel_task is not None:
                cancel_task.cancel()
                pending_tasks.append(cancel_task)
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            sent_frames = (
                sender_task.result()
                if sender_task in done and not sender_task.cancelled() and sender_task.exception() is None
                else 0
            )
            return sent_frames, []

        if cancel_task is not None:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)
        sent_frames, events = await asyncio.gather(sender_task, receiver_task)
        if cancel_event is not None and cancel_event.is_set():
            LOGGER.info("asr stream cancellation observed after gather; closing session")
            try:
                await session.cancel()
            except Exception:
                pass
            return sent_frames, []
    except BaseException:
        LOGGER.exception("asr stream task failed; cancelling session")
        sender_task.cancel()
        receiver_task.cancel()
        pending_tasks = [sender_task, receiver_task]
        if cancel_task is not None:
            cancel_task.cancel()
            pending_tasks.append(cancel_task)
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        try:
            await session.cancel()
        except Exception:
            pass
        raise
    return sent_frames, events


async def _watch_cancel_event(
    session: AsrSession,
    cancel_event: threading.Event,
) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(0.05)
    LOGGER.info("asr stream cancel watcher closing session")
    await session.cancel()


async def _send_prepared_frames(session: AsrSession, frames: Iterable[bytes]) -> int:
    sent_frames = 0
    for frame in frames:
        await session.send_audio(frame)
        sent_frames += 1
        LOGGER.debug("asr sent prepared frame sequence=%s size_bytes=%s", sent_frames, len(frame))
    await session.finish()
    LOGGER.info("asr sent finish marker prepared_frames=%s", sent_frames)
    return sent_frames


async def _send_source_frames(
    session: AsrSession,
    config: AsrSessionConfig,
    source: AudioChunkSource,
    *,
    on_processing: Callable[[], None] | None,
    on_capture_ready: Callable[[], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> int:
    loop = asyncio.get_running_loop()
    sent_frames = 0

    def capture_and_send() -> None:
        nonlocal sent_frames
        capture_ready_emitted = False
        pipeline = AudioCapturePipeline(
            source=source,
            audio_format=config.audio_format,
            frame_duration_ms=config.frame_duration_ms,
        )
        for frame in pipeline.frames():
            if cancel_event is not None and cancel_event.is_set():
                LOGGER.info("asr sender stopped before frame send due to cancel")
                return
            if on_capture_ready is not None and not capture_ready_emitted:
                capture_ready_emitted = True
                loop.call_soon_threadsafe(on_capture_ready)
            future = asyncio.run_coroutine_threadsafe(session.send_audio(frame.data), loop)
            future.result()
            sent_frames += 1
            LOGGER.debug("asr sent live frame sequence=%s size_bytes=%s", sent_frames, len(frame.data))

    await asyncio.to_thread(capture_and_send)
    if cancel_event is not None and cancel_event.is_set():
        LOGGER.info("asr sender closing session without finish because cancel was requested")
        await session.cancel()
        return sent_frames
    if on_processing is not None:
        on_processing()
    await session.finish()
    LOGGER.info("asr sent finish marker live_frames=%s", sent_frames)
    return sent_frames


async def _receive_session_events(
    session: AsrSession,
    on_event: Callable[[AsrEvent], None] | None,
    *,
    cancel_event: threading.Event | None = None,
) -> list[AsrEvent]:
    events: list[AsrEvent] = []
    if not hasattr(session, "receive_event"):
        return events

    while True:
        if cancel_event is not None and cancel_event.is_set():
            return events
        try:
            event = await session.receive_event()  # type: ignore[attr-defined]
        except TencentAsrStreamClosed as exc:
            if events:
                LOGGER.info(
                    "asr receive stream closed after events count=%s clean=%s code=%s reason=%s",
                    len(events),
                    exc.clean,
                    exc.code,
                    exc.reason,
                )
                final_event = _final_event_from_closed_stream(events)
                if final_event is not None:
                    events.append(final_event)
                    LOGGER.info(
                        "asr synthesized final event from closed stream segment=%s has_text=%s",
                        final_event.segment_index,
                        bool(final_event.text),
                    )
                    if on_event is not None and not (
                        cancel_event is not None and cancel_event.is_set()
                    ):
                        on_event(final_event)
                return events
            raise
        if cancel_event is not None and cancel_event.is_set():
            return events
        events.append(event)
        LOGGER.debug(
            "asr received event type=%s stable=%s final=%s segment=%s has_text=%s error_code=%s",
            event.type.value,
            event.stable,
            event.final,
            event.segment_index,
            bool(event.text),
            event.error_code,
        )
        if on_event is not None:
            on_event(event)
        if event.final or event.type.value == "error":
            break
    return events


def _final_event_from_closed_stream(events: list[AsrEvent]) -> AsrEvent | None:
    if not events:
        return None
    last_event = events[-1]
    if last_event.final or last_event.type == AsrEventType.ERROR:
        return None
    if not last_event.stable and last_event.type != AsrEventType.STABLE:
        return None
    return AsrEvent(
        type=AsrEventType.FINAL,
        text=last_event.text,
        stable=True,
        final=True,
        segment_index=last_event.segment_index,
        latency_ms=last_event.latency_ms,
    )
