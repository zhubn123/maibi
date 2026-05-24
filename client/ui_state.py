from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from core import AsrEvent, AsrEventType


DEFAULT_HOTKEY_LABEL = "Ctrl+Alt+Space"


class UiMode(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    ERROR = "error"
    CANCELLED = "cancelled"
    FINAL = "final"


class UiIntentKind(StrEnum):
    NO_ACTION = "no_action"
    CANCEL_INPUT = "cancel_input"
    CONFIRM_TEXT = "confirm_text"
    COPY_TEXT = "copy_text"
    OPEN_SETTINGS = "open_settings"
    QUIT = "quit"


@dataclass(frozen=True, slots=True)
class UiIntent:
    kind: UiIntentKind
    text: str = ""
    source: str | None = None

    @property
    def commits_text(self) -> bool:
        return self.kind == UiIntentKind.CONFIRM_TEXT and bool(self.text)


@dataclass(frozen=True, slots=True)
class ClientUiState:
    mode: UiMode = UiMode.IDLE
    partial_text: str = ""
    stable_text: str = ""
    final_text: str = ""
    active_segment_index: int | None = None
    active_segment_text: str = ""
    error_code: str | None = None
    error_message: str | None = None

    @property
    def active_text(self) -> str:
        if self.final_text:
            return self.final_text
        if self.stable_text and self.partial_text and self.active_segment_index is not None:
            return _join_text(state_text=self.stable_text, event_text=self.partial_text)
        return self.stable_text or self.partial_text

    @property
    def confirmable_text(self) -> str:
        return self.final_text or self.stable_text

    @property
    def can_confirm(self) -> bool:
        return self.mode != UiMode.ERROR and bool(self.confirmable_text)

    @property
    def can_cancel(self) -> bool:
        return self.mode in {
            UiMode.LISTENING,
            UiMode.PROCESSING,
            UiMode.ERROR,
            UiMode.FINAL,
        }

    @property
    def can_copy(self) -> bool:
        return self.mode in {UiMode.ERROR, UiMode.FINAL, UiMode.PROCESSING} and bool(self.active_text)


@dataclass(frozen=True, slots=True)
class TrayView:
    status_text: str
    tooltip: str
    primary_action_text: str
    settings_action_text: str = "设置"
    quit_action_text: str = "退出麦笔"


@dataclass(frozen=True, slots=True)
class FloatingWindowView:
    visible: bool
    title: str
    status_text: str
    primary_text: str
    helper_text: str
    confirm_action_text: str
    cancel_action_text: str
    copy_action_text: str
    can_confirm: bool
    can_cancel: bool
    can_copy: bool


_STATUS_TEXT: dict[UiMode, str] = {
    UiMode.IDLE: "就绪",
    UiMode.LISTENING: "正在听写",
    UiMode.PROCESSING: "正在识别",
    UiMode.ERROR: "识别失败",
    UiMode.CANCELLED: "已取消",
    UiMode.FINAL: "识别完成",
}

_TRAY_ACTION_TEXT: dict[UiMode, str] = {
    UiMode.IDLE: "开始语音输入",
    UiMode.LISTENING: "取消本次输入",
    UiMode.PROCESSING: "等待识别结果",
    UiMode.ERROR: "重试语音输入",
    UiMode.CANCELLED: "开始语音输入",
    UiMode.FINAL: "确认上屏",
}

_FLOATING_HELPER_TEXT: dict[UiMode, str] = {
    UiMode.IDLE: f"按住 {DEFAULT_HOTKEY_LABEL} 开始语音输入",
    UiMode.LISTENING: "松开快捷键后等待最终结果，Esc 取消，Enter 确认稳定文本",
    UiMode.PROCESSING: "正在等待最终识别结果，Esc 可取消本次输入",
    UiMode.ERROR: "请重试；如有已识别文本，可手动复制",
    UiMode.CANCELLED: "本次输入已取消，不会写入文本",
    UiMode.FINAL: "可确认上屏，也可手动复制文本",
}


def initial_state() -> ClientUiState:
    return ClientUiState()


def begin_listening() -> ClientUiState:
    return ClientUiState(mode=UiMode.LISTENING)


def begin_processing(state: ClientUiState) -> ClientUiState:
    return replace(
        state,
        mode=UiMode.PROCESSING,
        error_code=None,
        error_message=None,
    )


def reset_to_idle() -> ClientUiState:
    return ClientUiState()


def apply_asr_event(state: ClientUiState, event: AsrEvent) -> ClientUiState:
    if state.mode == UiMode.CANCELLED:
        return state

    if event.type == AsrEventType.ERROR:
        return replace(
            state,
            mode=UiMode.ERROR,
            error_code=event.error_code,
            error_message=_error_message(event),
        )

    if event.final or event.type == AsrEventType.FINAL:
        final_text = _merge_committed_text(state, event)
        return replace(
            state,
            mode=UiMode.FINAL,
            partial_text="",
            stable_text=final_text,
            final_text=final_text,
            active_segment_index=event.segment_index,
            active_segment_text=event.text,
            error_code=None,
            error_message=None,
        )

    if event.stable or event.type == AsrEventType.STABLE:
        stable_text = _merge_committed_text(state, event)
        return replace(
            state,
            mode=_live_result_mode(state),
            partial_text="",
            stable_text=stable_text,
            final_text="",
            active_segment_index=event.segment_index,
            active_segment_text=event.text,
            error_code=None,
            error_message=None,
        )

    partial_text = _partial_text(state, event)
    return replace(
        state,
        mode=_live_result_mode(state),
        partial_text=partial_text,
        final_text="",
        active_segment_index=event.segment_index,
        active_segment_text=event.text,
        error_code=None,
        error_message=None,
    )


def intent_from_key(state: ClientUiState, key: str) -> UiIntent:
    normalized_key = key.strip().lower()
    if normalized_key in {"esc", "escape"} and state.can_cancel:
        return UiIntent(UiIntentKind.CANCEL_INPUT, source=normalized_key)
    if normalized_key in {"enter", "return"} and state.can_confirm:
        return UiIntent(
            UiIntentKind.CONFIRM_TEXT,
            text=state.confirmable_text,
            source=normalized_key,
        )
    return UiIntent(UiIntentKind.NO_ACTION, source=normalized_key or None)


def intent_from_copy_action(state: ClientUiState) -> UiIntent:
    if state.can_copy:
        return UiIntent(UiIntentKind.COPY_TEXT, text=state.active_text, source="copy")
    return UiIntent(UiIntentKind.NO_ACTION, source="copy")


def apply_user_intent(state: ClientUiState, intent: UiIntent) -> ClientUiState:
    if intent.kind == UiIntentKind.CANCEL_INPUT:
        return ClientUiState(mode=UiMode.CANCELLED)
    if intent.kind == UiIntentKind.CONFIRM_TEXT and intent.text:
        return ClientUiState(
            mode=UiMode.FINAL,
            stable_text=intent.text,
            final_text=intent.text,
        )
    return state


def build_tray_view(state: ClientUiState) -> TrayView:
    status_text = _STATUS_TEXT[state.mode]
    return TrayView(
        status_text=status_text,
        tooltip=f"麦笔：{status_text}（{DEFAULT_HOTKEY_LABEL}）",
        primary_action_text=_TRAY_ACTION_TEXT[state.mode],
    )


def build_floating_window_view(state: ClientUiState) -> FloatingWindowView:
    status_text = _STATUS_TEXT[state.mode]
    primary_text = state.active_text
    helper_text = state.error_message or _FLOATING_HELPER_TEXT[state.mode]
    if not primary_text and state.mode == UiMode.LISTENING:
        primary_text = "正在等待语音..."
    if not primary_text and state.mode == UiMode.PROCESSING:
        primary_text = "正在整理识别结果..."
    if not primary_text and state.mode == UiMode.ERROR:
        primary_text = "没有可用识别文本"

    return FloatingWindowView(
        visible=state.mode != UiMode.IDLE,
        title="麦笔语音输入",
        status_text=status_text,
        primary_text=primary_text,
        helper_text=helper_text,
        confirm_action_text="确认上屏",
        cancel_action_text="取消",
        copy_action_text="复制文本",
        can_confirm=state.can_confirm,
        can_cancel=state.can_cancel,
        can_copy=state.can_copy,
    )


def _error_message(event: AsrEvent) -> str:
    if event.text:
        return event.text
    if event.error_code:
        return f"识别出错：{event.error_code}"
    return _FLOATING_HELPER_TEXT[UiMode.ERROR]


def _live_result_mode(state: ClientUiState) -> UiMode:
    if state.mode == UiMode.PROCESSING:
        return UiMode.PROCESSING
    return UiMode.LISTENING


def _merge_committed_text(state: ClientUiState, event: AsrEvent) -> str:
    if not event.text:
        return state.stable_text
    if event.segment_index is None:
        return event.text
    if _same_segment(state, event):
        return _replace_tail(
            state.stable_text,
            state.partial_text or state.active_segment_text,
            event.text,
        )
    return _join_text(state_text=state.stable_text, event_text=event.text)


def _partial_text(state: ClientUiState, event: AsrEvent) -> str:
    if _same_segment(state, event):
        return event.text
    return event.text


def _same_segment(state: ClientUiState, event: AsrEvent) -> bool:
    return (
        event.segment_index is not None
        and state.active_segment_index is not None
        and event.segment_index == state.active_segment_index
    )


def _replace_tail(stable_text: str, partial_text: str, event_text: str) -> str:
    if partial_text and stable_text.endswith(partial_text):
        return stable_text[: -len(partial_text)] + event_text
    return _join_text(state_text=stable_text, event_text=event_text)


def _join_text(*, state_text: str, event_text: str) -> str:
    if not state_text:
        return event_text
    if not event_text:
        return state_text
    if state_text.endswith((" ", "\n")) or event_text.startswith((" ", "\n")):
        return f"{state_text}{event_text}"
    return f"{state_text}{event_text}"


__all__ = [
    "ClientUiState",
    "DEFAULT_HOTKEY_LABEL",
    "FloatingWindowView",
    "TrayView",
    "UiIntent",
    "UiIntentKind",
    "UiMode",
    "apply_asr_event",
    "apply_user_intent",
    "begin_listening",
    "begin_processing",
    "build_floating_window_view",
    "build_tray_view",
    "initial_state",
    "intent_from_copy_action",
    "intent_from_key",
    "reset_to_idle",
]
