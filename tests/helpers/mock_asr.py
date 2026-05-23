from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from core import AsrEvent, AsrEventType, AsrSessionConfig


DEFAULT_AUDIO_EVENTS: tuple[AsrEvent, ...] = (
    AsrEvent(type=AsrEventType.PARTIAL, text="draft partial"),
    AsrEvent(type=AsrEventType.STABLE, text="stable text", stable=True),
)

DEFAULT_FINAL_EVENT = AsrEvent(
    type=AsrEventType.FINAL,
    text="final text",
    stable=True,
    final=True,
)


@dataclass(slots=True)
class MockStreamingAsrProvider:
    audio_events: Sequence[AsrEvent] = DEFAULT_AUDIO_EVENTS
    final_event: AsrEvent = DEFAULT_FINAL_EVENT
    sessions: list[MockStreamingAsrSession] = field(default_factory=list)

    async def start_session(self, config: AsrSessionConfig) -> MockStreamingAsrSession:
        session = MockStreamingAsrSession(
            config=config,
            audio_events=tuple(self.audio_events),
            final_event=self.final_event,
        )
        self.sessions.append(session)
        return session


@dataclass(slots=True)
class MockStreamingAsrSession:
    config: AsrSessionConfig
    audio_events: tuple[AsrEvent, ...] = DEFAULT_AUDIO_EVENTS
    final_event: AsrEvent = DEFAULT_FINAL_EVENT
    received_frame_sizes: list[int] = field(default_factory=list)
    finished: bool = False
    cancelled: bool = False
    _next_audio_event_index: int = 0
    _event_queue: asyncio.Queue[AsrEvent | None] = field(default_factory=asyncio.Queue)

    async def send_audio(self, frame: bytes) -> None:
        self._ensure_active()
        expected_size = self.config.frame_size_bytes
        if len(frame) != expected_size:
            raise ValueError(
                f"expected {expected_size} bytes for one "
                f"{self.config.frame_duration_ms}ms PCM frame, got {len(frame)}"
            )

        self.received_frame_sizes.append(len(frame))
        if self._next_audio_event_index < len(self.audio_events):
            event = self.audio_events[self._next_audio_event_index]
            self._next_audio_event_index += 1
            await self._event_queue.put(event)

    async def finish(self) -> None:
        self._ensure_active()
        self.finished = True
        await self._event_queue.put(self.final_event)
        await self._event_queue.put(None)

    async def cancel(self) -> None:
        if self.finished:
            raise RuntimeError("cannot cancel a finished ASR session")
        if self.cancelled:
            return

        self.cancelled = True
        await self._event_queue.put(None)

    async def receive_event(self) -> AsrEvent | None:
        return await self._event_queue.get()

    async def drain_events(self) -> list[AsrEvent]:
        events: list[AsrEvent] = []
        while True:
            event = await self.receive_event()
            if event is None:
                return events
            events.append(event)

    def _ensure_active(self) -> None:
        if self.finished:
            raise RuntimeError("cannot use a finished ASR session")
        if self.cancelled:
            raise RuntimeError("cannot use a cancelled ASR session")
