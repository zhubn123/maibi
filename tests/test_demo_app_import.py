import importlib.util
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from client.ui_state import ClientUiState, UiMode
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from client.demo_app import DemoWindow
from core import CommitResult, CommitStatus


class _FakeCommitter:
    def __init__(self, result: CommitResult) -> None:
        self.result = result
        self.committed_text: str | None = None
        self.target_handle: int | None = None

    def commit(self, text: str, target_handle: int | None = None) -> CommitResult:
        self.committed_text = text
        self.target_handle = target_handle
        return self.result


class _FakeWindowTargeter:
    def __init__(self, handle: int | None = 42) -> None:
        self.handle = handle
        self.captured = 0

    def capture_foreground(self) -> int | None:
        self.captured += 1
        return self.handle

    def restore_foreground(self, handle: int | None) -> None:
        pass


def _window(**kwargs) -> tuple[DemoWindow, None]:  # type: ignore[no-untyped-def]
    window = DemoWindow(**kwargs)
    return window, None


def test_demo_app_module_exists() -> None:
    assert importlib.util.find_spec("client.demo_app") is not None


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _flush_events() -> None:
    app = _app()
    app.processEvents()


def test_demo_window_session_failure_after_stable_text_keeps_success_result() -> None:
    _app()
    window, _bridge = _window()
    try:
        window.worker_generation = 1
        window.state = ClientUiState(mode=UiMode.PROCESSING, stable_text="已经识别")

        window._on_session_failed(1, "网络中断")

        assert window.state.mode == UiMode.FINAL
        assert window.state.active_text == "已经识别"
        assert window.state.can_confirm is True
        assert window.state.can_copy is True
    finally:
        window.close()


def test_demo_window_cancel_discards_preview_until_user_clears() -> None:
    _app()
    targeter = _FakeWindowTargeter(55)
    window, _bridge = _window(window_targeter=targeter)
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
    window, _bridge = _window()
    try:
        assert bool(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        assert bool(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        assert window.focusPolicy().name == "NoFocus"
        assert window.confirm_button.focusPolicy().name == "NoFocus"
    finally:
        window.close()


def test_demo_window_enter_commits_text_and_returns_to_idle() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window, _bridge = _window(text_committer=committer, window_targeter=_FakeWindowTargeter(77))
    try:
        window.commit_target_handle = 77
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="上屏文本", final_text="上屏文本")

        window._confirm_preview_text()

        assert committer.committed_text == "上屏文本"
        assert committer.target_handle == 77
        assert window.state.mode == UiMode.IDLE
        assert window.state.active_text == ""
    finally:
        window.close()


def test_demo_window_confirm_button_is_visible_entry_for_commit() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window, _bridge = _window(text_committer=committer, window_targeter=_FakeWindowTargeter(88))
    try:
        window.commit_target_handle = 88
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="按钮上屏", final_text="按钮上屏")
        window._render()

        assert window.confirm_button.isEnabled() is True
        assert window.confirm_button.text() == "确认上屏"

        window.confirm_button.click()

        assert committer.committed_text == "按钮上屏"
        assert committer.target_handle == 88
        assert window.state.mode == UiMode.IDLE
    finally:
        window.close()


def test_demo_window_start_recording_shows_wait_notice() -> None:
    _app()
    window, _bridge = _window(window_targeter=_FakeWindowTargeter(55))
    try:
        class _FakeWorker:
            def __init__(self, parent=None) -> None:
                self.state_changed = _FakeSignal()
                self.capture_ready = _FakeSignal()
                self.event_received = _FakeSignal()
                self.session_failed = _FakeSignal()
                self.session_finished = _FakeSignal()
                self.finished = _FakeSignal()
                self.started = False

            def start(self) -> None:
                self.started = True

            def isRunning(self) -> bool:
                return self.started

        class _FakeSignal:
            def connect(self, _callback) -> None:  # type: ignore[no-untyped-def]
                return None

        from client import demo_app as demo_module

        original_worker = demo_module.SessionWorker
        demo_module.SessionWorker = _FakeWorker  # type: ignore[assignment]
        try:
            window._start_recording()
        finally:
            demo_module.SessionWorker = original_worker  # type: ignore[assignment]

        assert window.state.mode == UiMode.LISTENING
        assert window.state.notice_message == "正在连接语音服务，请稍候"
    finally:
        window.close()


def test_demo_window_capture_ready_updates_notice() -> None:
    _app()
    window, _bridge = _window()
    try:
        window.worker_generation = 2
        window.state = ClientUiState(mode=UiMode.LISTENING, notice_message="正在连接语音服务，请稍候")

        window._on_capture_ready(2)

        assert window.capture_ready_generation == 2
        assert window.state.notice_message == "可以开始说话"
        assert window.helper_text.text() == "可以开始说话"
    finally:
        window.close()


def test_demo_window_stop_before_capture_ready_cancels_input() -> None:
    _app()
    window, _bridge = _window()

    class _FakeWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def isRunning(self) -> bool:
            return True

        def request_cancel(self) -> None:
            self.cancelled = True

    worker = _FakeWorker()
    try:
        window.worker = worker  # type: ignore[assignment]
        window.worker_generation = 3
        window.capture_ready_generation = None
        window.commit_target_handle = 55
        window.state = ClientUiState(mode=UiMode.LISTENING, notice_message="正在连接语音服务，请稍候")

        window._stop_recording()

        assert worker.cancelled is True
        assert window.worker_generation == 4
        assert window.capture_ready_generation is None
        assert window.commit_target_handle is None
        assert window.state.mode == UiMode.CANCELLED
    finally:
        window.worker = None
        window.close()


def test_demo_window_stop_after_capture_ready_shows_closing_notice_without_stable_text() -> None:
    _app()
    window, _bridge = _window()

    class _FakeWorker:
        def __init__(self) -> None:
            self.stopped = False

        def isRunning(self) -> bool:
            return True

        def request_stop(self) -> None:
            self.stopped = True

    worker = _FakeWorker()
    try:
        window.worker = worker  # type: ignore[assignment]
        window.worker_generation = 5
        window.capture_ready_generation = 5
        window.state = ClientUiState(mode=UiMode.LISTENING)

        window._stop_recording()

        assert worker.stopped is True
        assert window.state.mode == UiMode.PROCESSING
        assert window.state.notice_message == "正在结束录音并等待识别返回"
        assert window.helper_text.text() == "正在结束录音并等待识别返回"
    finally:
        window.worker = None
        window.close()


def test_demo_window_cancel_keeps_worker_until_thread_finishes() -> None:
    _app()
    window, _bridge = _window()

    class _FakeWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def isRunning(self) -> bool:
            return True

        def request_cancel(self) -> None:
            self.cancelled = True

    worker = _FakeWorker()
    try:
        window.worker = worker  # type: ignore[assignment]
        window.state = ClientUiState(mode=UiMode.PROCESSING, stable_text="待取消")

        window._cancel_input()

        assert worker.cancelled is True
        assert window.worker is worker
        assert window.state.mode == UiMode.CANCELLED
    finally:
        window.worker = None
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
