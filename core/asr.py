from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from core.config import AsrSessionConfig


class AsrEventType(StrEnum):
    PARTIAL = "partial"
    STABLE = "stable"
    FINAL = "final"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AsrEvent:
    type: AsrEventType
    text: str = ""
    stable: bool = False
    final: bool = False
    latency_ms: int | None = None
    error_code: str | None = None


class AsrSession(Protocol):
    async def send_audio(self, frame: bytes) -> None:
        """Send one PCM audio frame to the active ASR session."""

    async def finish(self) -> None:
        """Finish audio input and ask the provider for a final result."""

    async def cancel(self) -> None:
        """Cancel the active ASR session without committing text."""


class AsrProvider(Protocol):
    async def start_session(self, config: AsrSessionConfig) -> AsrSession:
        """Create a provider-backed streaming ASR session."""

