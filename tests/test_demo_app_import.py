import importlib.util
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from client.ui_state import ClientUiState, UiMode
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from client.hotkey import HotkeyAction
from client.demo_app import DemoWindow
from core import CommitResult, CommitStatus


class _FakeCommitter:
    def __init__(self, result: CommitResult) -> None:
        self.result = result
        self.committed_text: str | None = None

    def commit(self, text: str) -> CommitResult:
        self.committed_text = text
        return self.result


class _FakeHotkeyBridge(QObject):
    action_received = Signal(str)

    def __init__(self, active_getter, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.active_getter = active_getter
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def emit_action(self, action: HotkeyAction) -> None:
        self.action_received.emit(action.value)


def _window(**kwargs) -> tuple[DemoWindow, _FakeHotkeyBridge]:  # type: ignore[no-untyped-def]
    bridge: _FakeHotkeyBridge | None = None

    def factory(active_getter, parent):  # type: ignore[no-untyped-def]
        nonlocal bridge
        bridge = _FakeHotkeyBridge(active_getter, parent)
        return bridge

    window = DemoWindow(hotkey_bridge_factory=factory, **kwargs)
    assert bridge is not None
    return window, bridge


def test_demo_app_module_exists() -> None:
    assert importlib.util.find_spec("client.demo_app") is not None


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_demo_window_session_failure_preserves_preview_text_for_copy() -> None:
    _app()
    window, _bridge = _window()
    try:
        window.worker_generation = 1
        window.state = ClientUiState(mode=UiMode.PROCESSING, stable_text="已经识别")

        window._on_session_failed(1, "网络中断")

        assert window.state.mode.value == "error"
        assert window.state.active_text == "已经识别"
        assert window.state.can_copy is True
        assert window.state.can_confirm is False
    finally:
        window.close()


def test_demo_window_cancel_discards_preview_until_user_clears() -> None:
    _app()
    window, _bridge = _window()
    try:
        window.state = ClientUiState(mode=UiMode.PROCESSING, partial_text="临时文本")

        window._cancel_input()

        assert window.state.mode.value == "cancelled"
        assert window.state.active_text == ""
    finally:
        window.close()


def test_demo_window_copy_action_shows_success_notice() -> None:
    _app()
    window, _bridge = _window()
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="可复制", final_text="可复制")

        window._copy_preview_text()

        assert window.state.notice_message == "已复制"
        assert window.helper_text.text() == "已复制"
        assert QApplication.clipboard().text() == "可复制"
    finally:
        window.close()


def test_demo_window_uses_non_focus_tool_window_flags() -> None:
    _app()
    window, bridge = _window()
    try:
        assert bool(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        assert window.focusPolicy().name == "NoFocus"
        assert window.confirm_button.focusPolicy().name == "NoFocus"
        assert bridge.started is True
    finally:
        window.close()


def test_demo_window_enter_commits_text_and_returns_to_idle() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window, _bridge = _window(text_committer=committer)
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="上屏文本", final_text="上屏文本")

        window._confirm_preview_text()

        assert committer.committed_text == "上屏文本"
        assert window.state.mode == UiMode.IDLE
        assert window.state.active_text == ""
    finally:
        window.close()


def test_demo_window_confirm_button_is_visible_entry_for_commit() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window, _bridge = _window(text_committer=committer)
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="按钮上屏", final_text="按钮上屏")
        window._render()

        assert window.confirm_button.isEnabled() is True
        assert window.confirm_button.text() == "确认上屏"

        window.confirm_button.click()

        assert committer.committed_text == "按钮上屏"
        assert window.state.mode == UiMode.IDLE
    finally:
        window.close()


def test_demo_window_global_hotkey_actions_drive_recording_methods() -> None:
    _app()
    window, bridge = _window()
    calls: list[str] = []
    try:
        window._start_recording = lambda: calls.append("start")  # type: ignore[method-assign]
        window._stop_recording = lambda: calls.append("stop")  # type: ignore[method-assign]

        bridge.emit_action(HotkeyAction.START_RECORDING)
        bridge.emit_action(HotkeyAction.STOP_RECORDING)

        assert calls == ["start", "stop"]
    finally:
        window.close()


def test_demo_window_global_hotkey_confirm_commits_text() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window, bridge = _window(text_committer=committer)
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="热键上屏", final_text="热键上屏")

        bridge.emit_action(HotkeyAction.CONFIRM)

        assert committer.committed_text == "热键上屏"
        assert window.state.mode == UiMode.IDLE
    finally:
        window.close()


def test_demo_window_global_hotkey_cancel_discards_active_text() -> None:
    _app()
    window, bridge = _window()
    try:
        window.state = ClientUiState(mode=UiMode.PROCESSING, partial_text="取消文本")

        bridge.emit_action(HotkeyAction.CANCEL)

        assert window.state.mode == UiMode.CANCELLED
        assert window.state.active_text == ""
    finally:
        window.close()


def test_demo_window_enter_keeps_text_on_commit_failure() -> None:
    _app()
    committer = _FakeCommitter(
        CommitResult(
            status=CommitStatus.FAILED,
            error_code="commit_failed",
            message="文本上屏失败，请手动复制",
        )
    )
    window, _bridge = _window(text_committer=committer)
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="保留文本", final_text="保留文本")

        window._confirm_preview_text()

        assert committer.committed_text == "保留文本"
        assert window.state.mode == UiMode.ERROR
        assert window.state.active_text == "保留文本"
        assert window.state.can_copy is True
        assert window.helper_text.text() == "文本上屏失败，请手动复制"
    finally:
        window.close()
