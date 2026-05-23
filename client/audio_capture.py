from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Protocol

from core import AudioFrame, PcmAudioFormat, PcmFrameSplitter


class AudioChunkSource(Protocol):
    def chunks(self) -> Iterator[bytes]:
        """Yield raw PCM chunks captured from an audio input."""


@dataclass(frozen=True, slots=True)
class InMemoryAudioSource:
    chunks_data: tuple[bytes, ...]

    @classmethod
    def from_chunks(cls, chunks: Iterable[bytes]) -> InMemoryAudioSource:
        return cls(tuple(chunks))

    def chunks(self) -> Iterator[bytes]:
        yield from self.chunks_data


@dataclass(slots=True)
class AudioCapturePipeline:
    source: AudioChunkSource
    audio_format: PcmAudioFormat = PcmAudioFormat()
    frame_duration_ms: int = 200
    flush_tail: bool = False

    def frames(self) -> Iterator[AudioFrame]:
        splitter = PcmFrameSplitter(self.audio_format, self.frame_duration_ms)
        for chunk in self.source.chunks():
            yield from splitter.push(chunk)

        if self.flush_tail:
            tail = splitter.flush()
            if tail is not None:
                yield tail


@dataclass(frozen=True, slots=True)
class SoundDeviceCaptureConfig:
    sample_rate_hz: int = 16_000
    channels: int = 1
    dtype: str = "int16"
    block_duration_ms: int = 200
    max_chunks: int | None = None

    @property
    def audio_format(self) -> PcmAudioFormat:
        return PcmAudioFormat(
            sample_rate_hz=self.sample_rate_hz,
            bits_per_sample=16,
            channels=self.channels,
        )

    @property
    def block_size_samples(self) -> int:
        return self.sample_rate_hz * self.block_duration_ms // 1000


class SoundDeviceAudioSource:
    def __init__(self, config: SoundDeviceCaptureConfig | None = None) -> None:
        self.config = config or SoundDeviceCaptureConfig()

    def chunks(self) -> Iterator[bytes]:
        import queue

        import sounddevice

        chunks: queue.Queue[bytes | None] = queue.Queue()

        def callback(indata, _frames, _time, _status) -> None:  # type: ignore[no-untyped-def]
            chunks.put(bytes(indata))

        with sounddevice.RawInputStream(
            samplerate=self.config.sample_rate_hz,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.block_size_samples,
            callback=callback,
        ):
            seen_chunks = 0
            while True:
                chunk = chunks.get()
                if chunk is None:
                    return
                yield chunk
                seen_chunks += 1
                if self.config.max_chunks is not None and seen_chunks >= self.config.max_chunks:
                    return


@dataclass(slots=True)
class CallbackAudioSource:
    produce_chunks: Callable[[], Iterator[bytes]]

    def chunks(self) -> Iterator[bytes]:
        yield from self.produce_chunks()
