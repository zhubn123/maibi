from __future__ import annotations

import asyncio

import pytest

from core import AsrEventType, AsrSessionConfig
from tests.helpers.mock_asr import MockStreamingAsrProvider


def test_mock_asr_accepts_200ms_pcm_frames_and_streams_events_in_order() -> None:
    async def scenario() -> None:
        config = AsrSessionConfig()
        provider = MockStreamingAsrProvider()
        session = await provider.start_session(config)
        frame = b"\x00" * config.frame_size_bytes

        await session.send_audio(frame)
        partial = await session.receive_event()
        await session.send_audio(frame)
        stable = await session.receive_event()
        await session.finish()
        final = await session.receive_event()
        end = await session.receive_event()

        assert provider.sessions == [session]
        assert session.received_frame_sizes == [6_400, 6_400]
        assert config.frame_duration_ms == 200
        assert [partial.type, stable.type, final.type] == [
            AsrEventType.PARTIAL,
            AsrEventType.STABLE,
            AsrEventType.FINAL,
        ]
        assert partial.stable is False
        assert partial.final is False
        assert stable.stable is True
        assert stable.final is False
        assert final.stable is True
        assert final.final is True
        assert end is None
        assert session.finished is True
        assert session.cancelled is False

    asyncio.run(scenario())


def test_mock_asr_rejects_non_200ms_pcm_frame_size() -> None:
    async def scenario() -> None:
        config = AsrSessionConfig()
        session = await MockStreamingAsrProvider().start_session(config)

        with pytest.raises(ValueError, match="expected 6400 bytes"):
            await session.send_audio(b"\x00" * (config.frame_size_bytes - 1))

        assert session.received_frame_sizes == []
        assert session.finished is False
        assert session.cancelled is False

    asyncio.run(scenario())


def test_mock_asr_finish_emits_final_and_closes_session() -> None:
    async def scenario() -> None:
        config = AsrSessionConfig()
        session = await MockStreamingAsrProvider().start_session(config)

        await session.finish()
        events = await session.drain_events()

        assert [event.type for event in events] == [AsrEventType.FINAL]
        assert events[0].final is True
        assert session.finished is True
        with pytest.raises(RuntimeError, match="finished"):
            await session.send_audio(b"\x00" * config.frame_size_bytes)

    asyncio.run(scenario())


def test_mock_asr_cancel_closes_without_final_event() -> None:
    async def scenario() -> None:
        config = AsrSessionConfig()
        session = await MockStreamingAsrProvider().start_session(config)

        await session.send_audio(b"\x00" * config.frame_size_bytes)
        await session.cancel()
        events = await session.drain_events()

        assert [event.type for event in events] == [AsrEventType.PARTIAL]
        assert all(not event.final for event in events)
        assert session.cancelled is True
        assert session.finished is False
        with pytest.raises(RuntimeError, match="cancelled"):
            await session.finish()

    asyncio.run(scenario())
