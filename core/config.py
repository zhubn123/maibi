from __future__ import annotations

from dataclasses import dataclass, field

from core.audio import PcmAudioFormat

MAX_HOTWORDS = 128
MAX_HOTWORD_LENGTH = 64
DEFAULT_HOTWORD_WEIGHT = 8


@dataclass(frozen=True, slots=True)
class Hotword:
    text: str
    weight: int = DEFAULT_HOTWORD_WEIGHT

    def __post_init__(self) -> None:
        normalized = self.text.strip()
        if not normalized:
            raise ValueError("hotword text must not be empty")
        if any(char.isspace() for char in normalized):
            raise ValueError("hotword text must not contain whitespace")
        if len(normalized) > MAX_HOTWORD_LENGTH:
            raise ValueError("hotword text is too long")
        if self.weight <= 0:
            raise ValueError("hotword weight must be positive")
        object.__setattr__(self, "text", normalized)


@dataclass(frozen=True, slots=True)
class AsrSessionConfig:
    provider: str = "tencent"
    engine: str = "16k_zh"
    sample_rate_hz: int = 16_000
    bits_per_sample: int = 16
    channels: int = 1
    frame_duration_ms: int = 200
    hotwords: tuple[Hotword, ...] = field(default_factory=tuple)
    client_session_id: str | None = None

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.bits_per_sample <= 0:
            raise ValueError("bits_per_sample must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")
        if self.frame_duration_ms <= 0:
            raise ValueError("frame_duration_ms must be positive")
        if len(self.hotwords) > MAX_HOTWORDS:
            raise ValueError("too many hotwords")

    @property
    def frame_size_bytes(self) -> int:
        return self.audio_format.frame_size_bytes(self.frame_duration_ms)

    @property
    def audio_format(self) -> PcmAudioFormat:
        return PcmAudioFormat(
            sample_rate_hz=self.sample_rate_hz,
            bits_per_sample=self.bits_per_sample,
            channels=self.channels,
        )


@dataclass(frozen=True, slots=True)
class UsageLimitConfig:
    daily_limit_minutes: int = 60
    warning_ratio: float = 0.8

    def __post_init__(self) -> None:
        if self.daily_limit_minutes <= 0:
            raise ValueError("daily_limit_minutes must be positive")
        if not 0 < self.warning_ratio <= 1:
            raise ValueError("warning_ratio must be in (0, 1]")

