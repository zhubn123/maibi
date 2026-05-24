from core import AsrEvent, AsrEventType

from client.ui_state import (
    UiIntentKind,
    UiMode,
    apply_asr_event,
    apply_user_intent,
    begin_listening,
    begin_processing,
    build_floating_window_view,
    build_tray_view,
    initial_state,
    intent_from_copy_action,
    intent_from_key,
    with_notice,
)


def test_idle_views_expose_tray_ready_state_and_hide_floating_window() -> None:
    state = initial_state()

    tray = build_tray_view(state)
    floating = build_floating_window_view(state)

    assert tray.status_text == "就绪"
    assert "Ctrl+Alt+Space" in tray.tooltip
    assert tray.primary_action_text == "开始语音输入"
    assert floating.visible is False
    assert floating.status_text == "就绪"
    assert floating.can_confirm is False


def test_listening_state_shows_pending_voice_copy_and_escape_cancel_intent() -> None:
    state = begin_listening()

    floating = build_floating_window_view(state)
    escape_intent = intent_from_key(state, "Esc")

    assert state.mode == UiMode.LISTENING
    assert floating.visible is True
    assert floating.status_text == "正在听写"
    assert floating.primary_text == "正在等待语音..."
    assert escape_intent.kind == UiIntentKind.CANCEL_INPUT


def test_partial_and_stable_asr_events_update_preview_without_confirming_partial() -> None:
    state = begin_listening()

    partial_state = apply_asr_event(
        state,
        AsrEvent(type=AsrEventType.PARTIAL, text="这是中间"),
    )
    stable_state = apply_asr_event(
        partial_state,
        AsrEvent(type=AsrEventType.STABLE, text="这是稳定文本", stable=True),
    )

    assert partial_state.mode == UiMode.LISTENING
    assert partial_state.active_text == "这是中间"
    assert partial_state.can_confirm is False
    assert intent_from_key(partial_state, "Enter").kind == UiIntentKind.NO_ACTION
    assert stable_state.active_text == "这是稳定文本"
    assert stable_state.can_confirm is True
    assert intent_from_key(stable_state, "Enter").text == "这是稳定文本"


def test_indexed_asr_events_accumulate_stable_segments_until_clear() -> None:
    first = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="第一句。", stable=True, segment_index=0),
    )
    second_partial = apply_asr_event(
        first,
        AsrEvent(type=AsrEventType.PARTIAL, text="第二", segment_index=1),
    )
    second_stable = apply_asr_event(
        second_partial,
        AsrEvent(type=AsrEventType.STABLE, text="第二句。", stable=True, segment_index=1),
    )

    assert first.active_text == "第一句。"
    assert second_partial.active_text == "第一句。第二"
    assert second_partial.confirmable_text == "第一句。"
    assert second_stable.active_text == "第一句。第二句。"
    assert second_stable.confirmable_text == "第一句。第二句。"


def test_indexed_partial_updates_replace_current_preview_tail() -> None:
    first = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="第一句。", stable=True, segment_index=0),
    )
    partial = apply_asr_event(
        first,
        AsrEvent(type=AsrEventType.PARTIAL, text="第二", segment_index=1),
    )
    updated_partial = apply_asr_event(
        partial,
        AsrEvent(type=AsrEventType.PARTIAL, text="第二句", segment_index=1),
    )

    assert updated_partial.active_text == "第一句。第二句"
    assert updated_partial.stable_text == "第一句。"
    assert updated_partial.partial_text == "第二句"


def test_indexed_final_replaces_same_segment_stable_text_without_duplication() -> None:
    first = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="第一句。", stable=True, segment_index=0),
    )
    second_stable = apply_asr_event(
        first,
        AsrEvent(type=AsrEventType.STABLE, text="第二句。", stable=True, segment_index=1),
    )
    final = apply_asr_event(
        second_stable,
        AsrEvent(type=AsrEventType.FINAL, text="第二句。", stable=True, final=True, segment_index=1),
    )

    assert second_stable.active_text == "第一句。第二句。"
    assert final.active_text == "第一句。第二句。"
    assert final.final_text == "第一句。第二句。"


def test_release_hotkey_enters_processing_and_keeps_stable_text_confirmable() -> None:
    listening = begin_listening()
    stable_state = apply_asr_event(
        listening,
        AsrEvent(type=AsrEventType.STABLE, text="稳定内容", stable=True),
    )

    processing = begin_processing(stable_state)
    floating = build_floating_window_view(processing)

    assert processing.mode == UiMode.PROCESSING
    assert processing.confirmable_text == "稳定内容"
    assert floating.status_text == "正在识别"
    assert floating.can_confirm is True
    assert intent_from_key(processing, "Enter").text == "稳定内容"


def test_final_event_shows_final_text_and_confirm_intent_for_commit_layer() -> None:
    state = apply_asr_event(
        begin_processing(begin_listening()),
        AsrEvent(type=AsrEventType.FINAL, text="最终文本", stable=True, final=True),
    )

    tray = build_tray_view(state)
    floating = build_floating_window_view(state)
    enter_intent = intent_from_key(state, "Enter")

    assert state.mode == UiMode.FINAL
    assert tray.status_text == "识别完成"
    assert floating.primary_text == "最终文本"
    assert floating.can_confirm is True
    assert enter_intent.kind == UiIntentKind.CONFIRM_TEXT
    assert enter_intent.commits_text is True


def test_escape_applies_cancelled_state_and_ignores_late_asr_events() -> None:
    state = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="不要写入", stable=True),
    )

    cancelled = apply_user_intent(state, intent_from_key(state, "Escape"))
    late_final = apply_asr_event(
        cancelled,
        AsrEvent(type=AsrEventType.FINAL, text="迟到结果", stable=True, final=True),
    )
    floating = build_floating_window_view(late_final)

    assert cancelled.mode == UiMode.CANCELLED
    assert late_final.mode == UiMode.CANCELLED
    assert late_final.active_text == ""
    assert floating.can_confirm is False
    assert floating.helper_text == "本次输入已取消，不会写入文本"


def test_error_state_preserves_recognized_text_for_manual_copy() -> None:
    state = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.PARTIAL, text="可复制文本"),
    )

    error_state = apply_asr_event(
        state,
        AsrEvent(type=AsrEventType.ERROR, error_code="network_timeout"),
    )
    floating = build_floating_window_view(error_state)
    copy_intent = intent_from_copy_action(error_state)

    assert error_state.mode == UiMode.ERROR
    assert error_state.active_text == "可复制文本"
    assert error_state.can_confirm is False
    assert floating.status_text == "识别失败"
    assert floating.can_copy is True
    assert "network_timeout" in floating.helper_text
    assert copy_intent.kind == UiIntentKind.COPY_TEXT
    assert copy_intent.text == "可复制文本"


def test_error_after_stable_text_can_copy_but_not_confirm() -> None:
    state = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="稳定文本", stable=True, segment_index=0),
    )

    error_state = apply_asr_event(
        state,
        AsrEvent(type=AsrEventType.ERROR, text="网络中断", error_code="network_timeout"),
    )
    floating = build_floating_window_view(error_state)

    assert error_state.mode == UiMode.ERROR
    assert error_state.active_text == "稳定文本"
    assert error_state.can_confirm is False
    assert floating.can_confirm is False
    assert floating.can_copy is True
    assert intent_from_key(error_state, "Enter").kind == UiIntentKind.NO_ACTION
    assert intent_from_copy_action(error_state).text == "稳定文本"


def test_notice_message_overrides_helper_until_next_asr_event() -> None:
    state = apply_asr_event(
        begin_processing(begin_listening()),
        AsrEvent(type=AsrEventType.FINAL, text="最终文本", stable=True, final=True),
    )
    copied = with_notice(state, "已复制")
    next_state = apply_asr_event(
        copied,
        AsrEvent(type=AsrEventType.FINAL, text="新文本", stable=True, final=True),
    )

    assert build_floating_window_view(copied).helper_text == "已复制"
    assert next_state.notice_message is None
    assert build_floating_window_view(next_state).helper_text == "可确认上屏，也可手动复制文本"


def test_enter_confirm_applies_final_state_with_stable_text_only() -> None:
    state = apply_asr_event(
        begin_listening(),
        AsrEvent(type=AsrEventType.STABLE, text="提前确认", stable=True),
    )

    confirmed = apply_user_intent(state, intent_from_key(state, "return"))

    assert confirmed.mode == UiMode.FINAL
    assert confirmed.final_text == "提前确认"
    assert confirmed.can_confirm is True
