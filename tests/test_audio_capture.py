from client.audio_capture import (
    AudioCapturePipeline,
    InMemoryAudioSource,
    SoundDeviceCaptureConfig,
)
from core import PcmAudioFormat


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
