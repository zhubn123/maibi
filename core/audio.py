from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PcmAudioFormat:
    sample_rate_hz: int = 16_000
    bits_per_sample: int = 16
    channels: int = 1

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.bits_per_sample <= 0:
            raise ValueError("bits_per_sample must be positive")
        if self.bits_per_sample % 8 != 0:
            raise ValueError("bits_per_sample must be byte-aligned")
        if self.channels <= 0:
            raise ValueError("channels must be positive")

    @property
    def bytes_per_sample(self) -> int:
        return self.bits_per_sample // 8

    def frame_size_bytes(self, duration_ms: int) -> int:
        if duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        samples_per_frame = self.sample_rate_hz * duration_ms // 1000
        return samples_per_frame * self.bytes_per_sample * self.channels


@dataclass(frozen=True, slots=True)
class AudioFrame:
    data: bytes
    sequence: int
    duration_ms: int
    format: PcmAudioFormat

    @property
    def size_bytes(self) -> int:
        return len(self.data)


class PcmFrameSplitter:
    def __init__(self, audio_format: PcmAudioFormat, frame_duration_ms: int = 200) -> None:
        self.audio_format = audio_format
        self.frame_duration_ms = frame_duration_ms
        self.frame_size_bytes = audio_format.frame_size_bytes(frame_duration_ms)
        self._buffer = bytearray()
        self._next_sequence = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def push(self, chunk: bytes) -> Iterator[AudioFrame]:
        if not chunk:
            return iter(())

        self._buffer.extend(chunk)
        return self._pop_complete_frames()

    def flush(self) -> AudioFrame | None:
        if not self._buffer:
            return None

        data = bytes(self._buffer)
        self._buffer.clear()
        return self._make_frame(data)

    def _pop_complete_frames(self) -> Iterator[AudioFrame]:
        while len(self._buffer) >= self.frame_size_bytes:
            data = bytes(self._buffer[: self.frame_size_bytes])
            del self._buffer[: self.frame_size_bytes]
            yield self._make_frame(data)

    def _make_frame(self, data: bytes) -> AudioFrame:
        frame = AudioFrame(
            data=data,
            sequence=self._next_sequence,
            duration_ms=self.frame_duration_ms,
            format=self.audio_format,
        )
        self._next_sequence += 1
        return frame
