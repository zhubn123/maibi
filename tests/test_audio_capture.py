from client.audio_capture import (
    AudioCapturePipeline,
    InMemoryAudioSource,
    SoundDeviceAudioSource,
    SoundDeviceCaptureConfig,
)
from core import PcmAudioFormat
import threading


def test_capture_pipeline_splits_source_chunks_into_200ms_frames() -> None:
    audio_format = PcmAudioFormat()
    frame_size = audio_format.frame_size_bytes(200)
    source = InMemoryAudioSource.from_chunks(
        [
            b"\x01" * (frame_size + 10),
            b"\x02" * (frame_size - 10),
        ]
    )

    frames = list(AudioCapturePipeline(source=source).frames())

    assert [frame.sequence for frame in frames] == [0, 1]
    assert [frame.size_bytes for frame in frames] == [frame_size, frame_size]
    assert all(frame.duration_ms == 200 for frame in frames)


def test_capture_pipeline_drops_incomplete_tail_by_default() -> None:
    source = InMemoryAudioSource.from_chunks([b"\x01" * 100])

    assert list(AudioCapturePipeline(source=source).frames()) == []


def test_capture_pipeline_can_flush_incomplete_tail_for_diagnostics() -> None:
    source = InMemoryAudioSource.from_chunks([b"\x01" * 100])

    frames = list(AudioCapturePipeline(source=source, flush_tail=True).frames())

    assert len(frames) == 1
    assert frames[0].sequence == 0
    assert frames[0].size_bytes == 100


def test_sounddevice_config_matches_plan_defaults() -> None:
    config = SoundDeviceCaptureConfig()

    assert config.sample_rate_hz == 16_000
    assert config.channels == 1
    assert config.dtype == "int16"
    assert config.block_duration_ms == 200
    assert config.block_size_samples == 3_200
    assert config.audio_format.frame_size_bytes(200) == 6_400


def test_sounddevice_source_stops_before_yielding_buffer_when_stop_requested(monkeypatch) -> None:
    chunks = [b"a", b"b"]
    stop_event = threading.Event()

    class _FakeStream:
        def __init__(self, **kwargs) -> None:
            self.callback = kwargs["callback"]

        def __enter__(self):
            for chunk in chunks:
                self.callback(chunk, 0, None, None)
            stop_event.set()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class _FakeSoundDevice:
        RawInputStream = _FakeStream

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", _FakeSoundDevice())

    source = SoundDeviceAudioSource(
        SoundDeviceCaptureConfig(max_chunks=None),
        stop_event=stop_event,
    )

    assert list(source.chunks()) == []
