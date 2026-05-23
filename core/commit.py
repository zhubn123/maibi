from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CommitStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CommitResult:
    status: CommitStatus
    error_code: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == CommitStatus.SUCCESS


class TextCommitter(Protocol):
    def commit(self, text: str) -> CommitResult:
        """Commit recognized text to the current cursor target."""

