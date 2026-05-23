import pytest

from core import PcmAudioFormat, PcmFrameSplitter


def test_default_pcm_format_matches_asr_plan_frame_size() -> None:
    audio_format = PcmAudioFormat()

    assert audio_format.sample_rate_hz == 16_000
    assert audio_format.bits_per_sample == 16
    assert audio_format.channels == 1
    assert audio_format.frame_size_bytes(200) == 6_400


def test_frame_splitter_emits_200ms_frames_from_byte_stream() -> None:
    splitter = PcmFrameSplitter(PcmAudioFormat(), frame_duration_ms=200)
    frame_size = splitter.frame_size_bytes

    first_batch = list(splitter.push(b"\x01" * (frame_size + 10)))
    second_batch = list(splitter.push(b"\x02" * (frame_size - 10)))

    assert [frame.sequence for frame in first_batch + second_batch] == [0, 1]
    assert [frame.size_bytes for frame in first_batch + second_batch] == [
        frame_size,
        frame_size,
    ]
    assert splitter.buffered_bytes == 0


def test_frame_splitter_flushes_partial_tail_frame() -> None:
    splitter = PcmFrameSplitter(PcmAudioFormat(), frame_duration_ms=200)

    assert list(splitter.push(b"\x01" * 100)) == []
    tail = splitter.flush()

    assert tail is not None
    assert tail.sequence == 0
    assert tail.size_bytes == 100
    assert tail.duration_ms == 200
    assert splitter.buffered_bytes == 0
    assert splitter.flush() is None


def test_pcm_format_rejects_non_byte_aligned_samples() -> None:
    with pytest.raises(ValueError, match="byte-aligned"):
        PcmAudioFormat(bits_per_sample=12)
