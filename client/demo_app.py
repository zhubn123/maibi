from __future__ import annotations

import sys

from PySide6.QtCore import Qt
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

from client.session_runner import run_tencent_demo_session
from client.ui_state import (
    UiMode,
    apply_user_intent,
    build_floating_window_view,
    build_tray_view,
    intent_from_copy_action,
    intent_from_key,
    reset_to_idle,
)
from core import AsrSessionConfig, Hotword
from core.providers.tencent import (
    TencentAsrCredentials,
    TencentAsrProvider,
    TencentAsrUrlBuilder,
)


class DemoWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = reset_to_idle()
        self.tray: QSystemTrayIcon | None = None

        self.setWindowTitle("Maibi")
        self.setFixedSize(660, 168)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
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
        self.hint_text = QLabel("Esc 取消    Enter 确认    Copy 复制")

        self.run_button = QPushButton("开始一次演示")
        self.error_button = QPushButton("模拟错误")
        self.copy_button = QPushButton("复制")
        self.reset_button = QPushButton("收起")

        self._build_ui()
        self._connect_signals()
        self._init_tray()
        self._render()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: transparent;
            }
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
            QLabel {
                color: #111827;
            }
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
        self.hint_text.setStyleSheet("font-size: 12px; color: #6b7280;")
        top.addWidget(self.hint_text, 0, Qt.AlignmentFlag.AlignVCenter)
        shell_layout.addLayout(top)

        self.primary_text.setStyleSheet("font-size: 22px; font-weight: 600; color: #111827;")
        shell_layout.addWidget(self.primary_text)

        self.helper_text.setStyleSheet("font-size: 13px; color: #64748b;")
        shell_layout.addWidget(self.helper_text)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        for button in (
            self.run_button,
            self.error_button,
            self.copy_button,
            self.reset_button,
        ):
            controls.addWidget(button)
        controls.addStretch(1)
        shell_layout.addLayout(controls)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.run_button.clicked.connect(self._run_demo_session)
        self.error_button.clicked.connect(self._simulate_error)
        self.copy_button.clicked.connect(self._copy_preview_text)
        self.reset_button.clicked.connect(self._reset)

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(QIcon(), self)
        menu = QMenu(self)
        show_action = QAction("显示悬浮条", self)
        reset_action = QAction("回到就绪", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self.show)
        reset_action.triggered.connect(self._reset)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addAction(reset_action)
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
            self._apply_key("Esc")
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._apply_key("Enter")
            return
        super().keyPressEvent(event)

    def _run_demo_session(self) -> None:
        import asyncio
        import json

        class _FakeTransport:
            def __init__(self, messages: list[str]) -> None:
                self.messages = list(messages)
                self.sent: list[bytes] = []
                self.closed = False

            async def send(self, data: bytes) -> None:
                self.sent.append(data)

            async def recv(self) -> str:
                return self.messages.pop(0)

            async def close(self) -> None:
                self.closed = True

        class _FakeDialer:
            def __init__(self, transport: _FakeTransport) -> None:
                self.transport = transport

            async def connect(self, _url: str):
                return self.transport

        async def scenario() -> None:
            provider = TencentAsrProvider(
                TencentAsrUrlBuilder(
                    TencentAsrCredentials(
                        appid="123456",
                        secret_id="demo-secret-id",
                        secret_key="demo-secret-key",
                    )
                ),
                dialer=_FakeDialer(
                    _FakeTransport(
                        [
                            json.dumps(
                                {
                                    "code": 0,
                                    "result": {
                                        "voice_text_str": "这是当前稳定结果",
                                        "slice_type": 2,
                                        "final": 0,
                                    },
                                }
                            ),
                            json.dumps(
                                {
                                    "code": 0,
                                    "result": {
                                        "voice_text_str": "这是最终上屏文本，已经可以确认输入。",
                                        "slice_type": 2,
                                        "final": 1,
                                    },
                                }
                            ),
                        ]
                    )
                ),
            )
            config = AsrSessionConfig(hotwords=(Hotword("麦笔"),))
            frame = b"\x00" * config.frame_size_bytes
            result = await run_tencent_demo_session(provider, config, [frame, frame])
            self.state = result.final_state

        asyncio.run(scenario())
        self._render()

    def _simulate_error(self) -> None:
        self.state = reset_to_idle()
        self.state = self.state.__class__(
            mode=UiMode.ERROR,
            partial_text="网络有波动，保留这段识别文本",
            error_code="demo_timeout",
            error_message="识别出错：demo_timeout",
        )
        self._render()

    def _apply_key(self, key: str) -> None:
        self.state = apply_user_intent(self.state, intent_from_key(self.state, key))
        self._render()

    def _copy_preview_text(self) -> None:
        intent = intent_from_copy_action(self.state)
        if intent.text:
            QGuiApplication.clipboard().setText(intent.text)

    def _reset(self) -> None:
        self.state = reset_to_idle()
        self._render()
        self.hide()

    def _render(self) -> None:
        tray_view = build_tray_view(self.state)
        floating_view = build_floating_window_view(self.state)

        self.status_text.setText(tray_view.tooltip)
        self.primary_text.setText(floating_view.primary_text or "按开始一次演示查看语音输入流程")
        self.helper_text.setText(floating_view.helper_text)
        self.copy_button.setEnabled(floating_view.can_copy)

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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = DemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
