import pytest

from core import (
    AsrEvent,
    AsrEventType,
    AsrSessionConfig,
    CommitResult,
    CommitStatus,
    Hotword,
    UsageLimitConfig,
)
from core.config import MAX_HOTWORDS


def test_asr_session_config_defaults_match_plan() -> None:
    config = AsrSessionConfig()

    assert config.provider == "tencent"
    assert config.engine == "16k_zh"
    assert config.sample_rate_hz == 16_000
    assert config.bits_per_sample == 16
    assert config.channels == 1
    assert config.frame_duration_ms == 200
    assert config.frame_size_bytes == 6_400


def test_hotword_normalizes_and_uses_default_weight() -> None:
    hotword = Hotword(" 麦笔 ")

    assert hotword.text == "麦笔"
    assert hotword.weight == 8


@pytest.mark.parametrize("text", ["", "   ", "客户 名称"])
def test_hotword_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        Hotword(text)


def test_asr_session_config_rejects_too_many_hotwords() -> None:
    hotwords = tuple(Hotword(f"词{i}") for i in range(MAX_HOTWORDS + 1))

    with pytest.raises(ValueError, match="too many hotwords"):
        AsrSessionConfig(hotwords=hotwords)


def test_asr_event_can_represent_final_text() -> None:
    event = AsrEvent(type=AsrEventType.FINAL, text="测试文本", stable=True, final=True)

    assert event.text == "测试文本"
    assert event.stable is True
    assert event.final is True


def test_commit_result_ok_reflects_status() -> None:
    assert CommitResult(status=CommitStatus.SUCCESS).ok is True
    assert CommitResult(status=CommitStatus.FAILED, error_code="clipboard_failed").ok is False


def test_usage_limit_defaults() -> None:
    config = UsageLimitConfig()

    assert config.daily_limit_minutes == 60
    assert config.warning_ratio == 0.8

