import importlib.util
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from client.ui_state import ClientUiState, UiMode
from PySide6.QtWidgets import QApplication

from client.demo_app import DemoWindow
from core import CommitResult, CommitStatus


class _FakeCommitter:
    def __init__(self, result: CommitResult) -> None:
        self.result = result
        self.committed_text: str | None = None

    def commit(self, text: str) -> CommitResult:
        self.committed_text = text
        return self.result


def test_demo_app_module_exists() -> None:
    assert importlib.util.find_spec("client.demo_app") is not None


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_demo_window_session_failure_preserves_preview_text_for_copy() -> None:
    _app()
    window = DemoWindow()
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
    window = DemoWindow()
    try:
        window.state = ClientUiState(mode=UiMode.PROCESSING, partial_text="临时文本")

        window._cancel_input()

        assert window.state.mode.value == "cancelled"
        assert window.state.active_text == ""
    finally:
        window.close()


def test_demo_window_copy_action_shows_success_notice() -> None:
    _app()
    window = DemoWindow()
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="可复制", final_text="可复制")

        window._copy_preview_text()

        assert window.state.notice_message == "已复制"
        assert window.helper_text.text() == "已复制"
        assert QApplication.clipboard().text() == "可复制"
    finally:
        window.close()


def test_demo_window_enter_commits_text_and_returns_to_idle() -> None:
    _app()
    committer = _FakeCommitter(CommitResult(status=CommitStatus.SUCCESS))
    window = DemoWindow(text_committer=committer)
    try:
        window.state = ClientUiState(mode=UiMode.FINAL, stable_text="上屏文本", final_text="上屏文本")

        window._confirm_preview_text()

        assert committer.committed_text == "上屏文本"
        assert window.state.mode == UiMode.IDLE
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
    window = DemoWindow(text_committer=committer)
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
