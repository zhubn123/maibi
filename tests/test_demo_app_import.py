import importlib.util
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from client.ui_state import ClientUiState, UiMode
from PySide6.QtWidgets import QApplication

from client.demo_app import DemoWindow


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
