from __future__ import annotations

import asyncio
import logging
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from client.audio_capture import SoundDeviceAudioSource, SoundDeviceCaptureConfig
from client.session_bootstrap import SessionBootstrapClient
from client.session_runner import run_bootstrapped_tencent_stream_session
from client.text_commit import WindowTargeter, Win32WindowTargeter, create_default_text_committer
from client.ui_state import (
    UiMode,
    apply_asr_event,
    apply_user_intent,
    begin_listening,
    begin_processing,
    build_floating_window_view,
    build_tray_view,
    intent_from_copy_action,
    intent_from_key,
    reset_to_idle,
    with_error,
    with_notice,
)
from core import AsrEvent, AsrEventType, AsrSessionConfig, Hotword
from core.commit import TextCommitter
from core.providers.tencent import WebSocketsTencentDialer

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DragState:
    offset_x: int
    offset_y: int


class SessionWorker(QThread):
    event_received = Signal(object)
    state_changed = Signal(str)
    capture_ready = Signal()
    session_failed = Signal(str)
    session_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stop_requested = threading.Event()
        self._cancel_requested = threading.Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def request_cancel(self) -> None:
        self._cancel_requested.set()
        self._stop_requested.set()

    def run(self) -> None:
        async def scenario() -> None:
            if self._cancel_requested.is_set():
                return
            config = AsrSessionConfig(
                hotwords=(Hotword("麦笔"),),
                client_session_id=f"maibi-demo-{uuid.uuid4().hex}",
            )
            bootstrap = SessionBootstrapClient()
            session_info = await bootstrap.create_tencent_session(config)
            if self._cancel_requested.is_set():
                return
            LOGGER.info("session worker bootstrapped websocket_url received")
            await run_bootstrapped_tencent_stream_session(
                websocket_url=session_info.websocket_url,
                config=config,
                source=SoundDeviceAudioSource(
                    SoundDeviceCaptureConfig(
                        sample_rate_hz=config.sample_rate_hz,
                        channels=config.channels,
                        block_duration_ms=config.frame_duration_ms,
                        max_chunks=None,
                    ),
                    stop_event=self._stop_requested,
                ),
                dialer=WebSocketsTencentDialer(),
                on_event=lambda event: self.event_received.emit(event),
                on_processing=lambda: self.state_changed.emit("processing"),
                cancel_event=self._cancel_requested,
                on_capture_ready=lambda: self.capture_ready.emit(),
            )

        try:
            asyncio.run(scenario())
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("session worker failed")
            message = traceback.format_exc(limit=4).strip()
            self.session_failed.emit(message or str(exc).strip())
            return
        self.session_finished.emit()


class DemoWindow(QMainWindow):
    def __init__(
        self,
        text_committer: TextCommitter | None = None,
        *,
        window_targeter: WindowTargeter | None = None,
    ) -> None:
        super().__init__()
        self.state = reset_to_idle()
        self.tray: QSystemTrayIcon | None = None
        self.drag_state: DragState | None = None
        self.worker: SessionWorker | None = None
        self.worker_generation = 0
        self.capture_ready_generation: int | None = None
        self.text_committer = text_committer
        self.window_targeter = window_targeter
        self.commit_target_handle: int | None = None

        self.setWindowTitle("Maibi")
        self.setFixedSize(640, 154)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.shell = QFrame()
        self.shell.setObjectName("shell")
        self.status_dot = QFrame()
        self.status_dot.setObjectName("statusDot")
        self.status_text = QLabel()
        self.primary_text = QLabel()
        self.primary_text.setWordWrap(True)
        self.helper_text = QLabel()
        self.helper_text.setWordWrap(True)

        self.hold_button = QPushButton("按住说话")
        self.confirm_button = QPushButton("确认上屏")
        self.copy_button = QPushButton("复制")
        self.clear_button = QPushButton("清除")
        for button in (self.hold_button, self.confirm_button, self.copy_button, self.clear_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._build_ui()
        self._connect_signals()
        self._init_tray()
        self._render()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: transparent; }
            QFrame#shell {
                background: #f7f8fa;
                border: 1px solid #d7dce5;
                border-radius: 10px;
            }
            QFrame#statusDot {
                min-width: 10px;
                max-width: 10px;
                min-height: 10px;
                max-height: 10px;
                border-radius: 5px;
                background: #64748b;
            }
            QLabel { color: #111827; }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d7dce5;
                border-radius: 6px;
                padding: 5px 10px;
                min-height: 30px;
            }
            QPushButton:disabled {
                color: #9ca3af;
                background: #f3f4f6;
            }
            """
        )

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addWidget(self.shell)

        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(14, 12, 14, 12)
        shell_layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status_text.setStyleSheet("font-size: 12px; color: #475569;")
        top.addWidget(self.status_text, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        shell_layout.addLayout(top)

        self.primary_text.setStyleSheet("font-size: 22px; font-weight: 600; color: #111827;")
        shell_layout.addWidget(self.primary_text)

        self.helper_text.setStyleSheet("font-size: 13px; color: #64748b;")
        shell_layout.addWidget(self.helper_text)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        for button in (self.hold_button, self.confirm_button, self.copy_button, self.clear_button):
            controls.addWidget(button)
        controls.addStretch(1)
        shell_layout.addLayout(controls)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.hold_button.pressed.connect(self._start_recording)
        self.hold_button.released.connect(self._stop_recording)
        self.confirm_button.clicked.connect(self._confirm_preview_text)
        self.copy_button.clicked.connect(self._copy_preview_text)
        self.clear_button.clicked.connect(self._clear_text)

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(QIcon(), self)
        menu = QMenu(self)
        show_action = QAction("显示悬浮条", self)
        clear_action = QAction("清除状态", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self.show)
        clear_action.triggered.connect(self._clear_text)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addAction(clear_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.setVisible(not self.isVisible())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray is not None and self.tray.isVisible():
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_input()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._confirm_preview_text()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint()
            top_left = self.frameGeometry().topLeft()
            self.drag_state = DragState(
                offset_x=position.x() - top_left.x(),
                offset_y=position.y() - top_left.y(),
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.drag_state is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint()
            self.move(
                position.x() - self.drag_state.offset_x,
                position.y() - self.drag_state.offset_y,
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_state = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _start_recording(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            LOGGER.info("demo start recording ignored because worker is still running")
            return

        self.worker_generation += 1
        generation = self.worker_generation
        self.commit_target_handle = self._window_targeter().capture_foreground()
        LOGGER.info(
            "demo start recording generation=%s target_handle=%s",
            generation,
            self.commit_target_handle,
        )
        self.state = begin_listening()
        self.state = with_notice(self.state, "正在连接语音服务，请稍候")
        self.capture_ready_generation = None
        self._render()
        self.worker = SessionWorker(parent=self)
        worker = self.worker
        worker.state_changed.connect(lambda state_name: self._on_worker_state_changed(generation, state_name))
        worker.capture_ready.connect(lambda: self._on_capture_ready(generation))
        worker.event_received.connect(lambda event: self._on_event_received(generation, event))
        worker.session_failed.connect(lambda message: self._on_session_failed(generation, message))
        worker.session_finished.connect(lambda: self._on_session_finished(generation))
        worker.finished.connect(lambda: self._on_worker_thread_finished(worker))
        worker.start()

    def _stop_recording(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            LOGGER.info("demo stop recording ignored because no worker is running")
            return
        LOGGER.info("demo stop recording generation=%s", self.worker_generation)
        if self.capture_ready_generation != self.worker_generation:
            LOGGER.info("demo stop recording before capture ready; cancelling generation=%s", self.worker_generation)
            self.worker.request_cancel()
            self.worker_generation += 1
            self.commit_target_handle = None
            self.capture_ready_generation = None
            self.state = apply_user_intent(self.state, intent_from_key(self.state, "Esc"))
            self._render()
            return
        self.worker.request_stop()
        self.state = begin_processing(self.state)
        if self.state.mode == UiMode.PROCESSING:
            self.state = with_notice(self.state, "正在结束录音并等待识别返回")
        self._render()

    def _on_worker_state_changed(self, generation: int, state_name: str) -> None:
        if generation != self.worker_generation:
            return
        if state_name == "processing":
            self.state = begin_processing(self.state)
            self._render()

    def _on_capture_ready(self, generation: int) -> None:
        if generation != self.worker_generation:
            return
        LOGGER.info("demo capture ready generation=%s", generation)
        self.capture_ready_generation = generation
        self.state = with_notice(self.state, "可以开始说话")
        self._render()

    def _on_event_received(self, generation: int, event) -> None:
        if generation != self.worker_generation:
            return
        self.state = apply_asr_event(self.state, event)
        self._render()

    def _on_session_finished(self, generation: int) -> None:
        if generation != self.worker_generation:
            return
        self.worker = None
        self.capture_ready_generation = None
        self._render()

    def _on_worker_thread_finished(self, worker: SessionWorker) -> None:
        if self.worker is worker:
            self.worker = None
            self.capture_ready_generation = None
            self._render()

    def _on_session_failed(self, generation: int, message: str) -> None:
        if generation != self.worker_generation:
            return
        self.state = apply_asr_event(
            self.state,
            AsrEvent(
                type=AsrEventType.ERROR,
                text=message,
                error_code="bootstrap_or_ws_failed",
            ),
        )
        self.worker = None
        self.capture_ready_generation = None
        self._render()

    def _confirm_preview_text(self) -> None:
        intent = intent_from_key(self.state, "Enter")
        if not intent.commits_text:
            LOGGER.info("demo confirm ignored mode=%s", self.state.mode.value)
            return
        LOGGER.info(
            "demo confirm requested mode=%s worker_running=%s target_handle=%s",
            self.state.mode.value,
            self.worker is not None and self.worker.isRunning(),
            self.commit_target_handle,
        )
        next_state = apply_user_intent(self.state, intent)
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_cancel()
        self.worker_generation += 1
        self.capture_ready_generation = None
        if intent.text:
            committer = self._text_committer()
            result = committer.commit(intent.text, target_handle=self.commit_target_handle)
            if result.ok:
                self.commit_target_handle = None
                self.state = reset_to_idle()
                self._render()
                return
            self.state = with_error(
                next_state,
                message=result.message or "文本上屏失败，请手动复制",
                error_code=result.error_code or "commit_failed",
            )
            self._render()
            return
        self.state = next_state
        self._render()

    def _cancel_input(self) -> None:
        next_state = apply_user_intent(self.state, intent_from_key(self.state, "Esc"))
        if next_state == self.state:
            LOGGER.info("demo cancel ignored mode=%s", self.state.mode.value)
            return
        LOGGER.info(
            "demo cancel requested mode=%s worker_running=%s",
            self.state.mode.value,
            self.worker is not None and self.worker.isRunning(),
        )
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_cancel()
        self.worker_generation += 1
        self.commit_target_handle = None
        self.capture_ready_generation = None
        self.state = next_state
        self._render()

    def _copy_preview_text(self) -> None:
        intent = intent_from_copy_action(self.state)
        if intent.text:
            try:
                QGuiApplication.clipboard().setText(intent.text)
            except Exception:  # pragma: no cover - Qt clipboard failure is platform dependent
                self.state = with_notice(self.state, "复制失败，请手动选择文本")
            else:
                self.state = with_notice(self.state, "已复制")
            self._render()

    def _text_committer(self) -> TextCommitter:
        if self.text_committer is None:
            self.text_committer = create_default_text_committer()
        return self.text_committer

    def _window_targeter(self) -> WindowTargeter:
        if self.window_targeter is None:
            self.window_targeter = Win32WindowTargeter()
        return self.window_targeter

    def _clear_text(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_cancel()
        self.worker_generation += 1
        self.commit_target_handle = None
        self.capture_ready_generation = None
        self.state = reset_to_idle()
        self._render()

    def _render(self) -> None:
        tray_view = build_tray_view(self.state)
        floating_view = build_floating_window_view(self.state)

        self.status_text.setText(tray_view.tooltip)
        self.primary_text.setText(floating_view.primary_text or "按住说话，松开结束")
        self.helper_text.setText(floating_view.helper_text)
        self.hold_button.setEnabled(True)
        self.confirm_button.setEnabled(floating_view.can_confirm)
        self.confirm_button.setText(floating_view.confirm_action_text)
        self.copy_button.setEnabled(floating_view.can_copy)
        self.clear_button.setEnabled(self.state.mode != UiMode.IDLE or self.worker is not None)

        color = {
            UiMode.IDLE: "#64748b",
            UiMode.LISTENING: "#2563eb",
            UiMode.PROCESSING: "#f59e0b",
            UiMode.ERROR: "#dc2626",
            UiMode.CANCELLED: "#6b7280",
            UiMode.FINAL: "#16a34a",
        }[self.state.mode]
        self.status_dot.setStyleSheet(
            f"background: {color}; min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px; border-radius: 5px;"
        )

        if self.tray is not None:
            self.tray.setToolTip(tray_view.tooltip)

        if self.state.mode != UiMode.IDLE:
            self.show()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = DemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
