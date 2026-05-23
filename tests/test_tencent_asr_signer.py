from urllib.parse import parse_qs, urlsplit

from core import AsrSessionConfig, Hotword
from core.providers.tencent import (
    TencentAsrCredentials,
    TencentAsrUrlBuilder,
    format_hotword_list,
    redact_signed_url,
)


def test_format_hotword_list_uses_tencent_weight_syntax() -> None:
    hotwords = (Hotword("麦笔"), Hotword("客户名称", weight=6))

    assert format_hotword_list(hotwords) == "麦笔|8,客户名称|6"


def test_tencent_url_builder_adds_expected_default_params() -> None:
    builder = TencentAsrUrlBuilder(
        TencentAsrCredentials(
            appid="123456",
            secret_id="secret-id",
            secret_key="secret-key",
        )
    )
    config = AsrSessionConfig(hotwords=(Hotword("麦笔"),))

    url = builder.build_url(config, now=1_700_000_000, nonce=42)
    split = urlsplit(url)
    params = parse_qs(split.query)

    assert split.scheme == "wss"
    assert split.netloc == "asr.cloud.tencent.com"
    assert split.path == "/asr/v2/123456"
    assert params["engine_model_type"] == ["16k_zh"]
    assert params["voice_format"] == ["1"]
    assert params["needvad"] == ["1"]
    assert params["vad_silence_time"] == ["1000"]
    assert params["filter_modal"] == ["1"]
    assert params["secretid"] == ["secret-id"]
    assert params["timestamp"] == ["1700000000"]
    assert params["expired"] == ["1700000300"]
    assert params["nonce"] == ["42"]
    assert params["hotword_list"] == ["麦笔|8"]
    assert params["signature"]


def test_tencent_url_signature_is_deterministic_for_fixed_inputs() -> None:
    credentials = TencentAsrCredentials(
        appid="123456",
        secret_id="secret-id",
        secret_key="secret-key",
    )
    builder = TencentAsrUrlBuilder(credentials)
    config = AsrSessionConfig(client_session_id="session-1")

    assert builder.build_url(config, now=1_700_000_000, nonce=42) == builder.build_url(
        config,
        now=1_700_000_000,
        nonce=42,
    )


def test_redact_signed_url_hides_sensitive_query_values() -> None:
    builder = TencentAsrUrlBuilder(
        TencentAsrCredentials(
            appid="123456",
            secret_id="secret-id",
            secret_key="secret-key",
        )
    )
    url = builder.build_url(
        AsrSessionConfig(hotwords=(Hotword("客户名称"),)),
        now=1_700_000_000,
        nonce=42,
    )

    redacted = redact_signed_url(url)

    assert "secret-id" not in redacted
    assert "signature=" in redacted
    assert "hotword_list=" in redacted
    assert "%3Credacted%3E" in redacted
    assert "客户名称" not in redacted
    assert "secret-key" not in url
