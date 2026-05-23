from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.ui_state import (
    ClientUiState,
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
)
from core import AsrEvent, AsrEventType


class DemoWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.state = reset_to_idle()
        self.tray: QSystemTrayIcon | None = None

        self.setWindowTitle("Maibi Demo Shell")
        self.setMinimumSize(620, 360)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self.status_pill = QLabel()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(120)
        self.helper = QLabel()
        self.helper.setWordWrap(True)

        self.listen_button = QPushButton("Listening")
        self.processing_button = QPushButton("Processing")
        self.final_button = QPushButton("Final")
        self.error_button = QPushButton("Error")
        self.enter_button = QPushButton("Enter")
        self.escape_button = QPushButton("Esc")
        self.copy_button = QPushButton("Copy")
        self.reset_button = QPushButton("Reset")

        self._build_ui()
        self._connect_signals()
        self._init_tray()
        self._render()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Maibi demo shell")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.status_pill.setStyleSheet(
            "padding: 6px 10px; border-radius: 999px; background: #1f2937; color: white;"
        )
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.status_pill)
        layout.addLayout(header)

        preview_frame = QFrame()
        preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.addWidget(self.preview)
        preview_layout.addWidget(self.helper)
        layout.addWidget(preview_frame)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(10)
        buttons = [
            self.listen_button,
            self.processing_button,
            self.final_button,
            self.error_button,
            self.enter_button,
            self.escape_button,
            self.copy_button,
            self.reset_button,
        ]
        for index, button in enumerate(buttons):
            controls.addWidget(button, index // 4, index % 4)
        layout.addLayout(controls)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.listen_button.clicked.connect(self._simulate_listening)
        self.processing_button.clicked.connect(self._simulate_processing)
        self.final_button.clicked.connect(self._simulate_final)
        self.error_button.clicked.connect(self._simulate_error)
        self.enter_button.clicked.connect(lambda: self._apply_key("Enter"))
        self.escape_button.clicked.connect(lambda: self._apply_key("Esc"))
        self.copy_button.clicked.connect(self._copy_preview_text)
        self.reset_button.clicked.connect(self._reset)

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(QIcon(), self)
        menu = QMenu(self)
        show_action = QAction("Show window", self)
        hide_action = QAction("Hide window", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self.show)
        hide_action.triggered.connect(self.hide)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addAction(hide_action)
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

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self._apply_key("Esc")
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._apply_key("Enter")
            return
        super().keyPressEvent(event)

    def _simulate_listening(self) -> None:
        self.state = begin_listening()
        self.state = apply_asr_event(
            self.state,
            AsrEvent(type=AsrEventType.PARTIAL, text="This is a live partial transcript."),
        )
        self.state = apply_asr_event(
            self.state,
            AsrEvent(type=AsrEventType.STABLE, text="This is stable recognized text.", stable=True),
        )
        self._render()

    def _simulate_processing(self) -> None:
        if self.state.mode == UiMode.IDLE:
            self._simulate_listening()
        self.state = begin_processing(self.state)
        self._render()

    def _simulate_final(self) -> None:
        if self.state.mode == UiMode.IDLE:
            self._simulate_processing()
        self.state = apply_asr_event(
            self.state,
            AsrEvent(
                type=AsrEventType.FINAL,
                text="This is the final commit-ready text.",
                stable=True,
                final=True,
            ),
        )
        self._render()

    def _simulate_error(self) -> None:
        if self.state.mode == UiMode.IDLE:
            self._simulate_listening()
        self.state = apply_asr_event(
            self.state,
            AsrEvent(type=AsrEventType.ERROR, error_code="demo_timeout"),
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

    def _render(self) -> None:
        tray_view = build_tray_view(self.state)
        floating_view = build_floating_window_view(self.state)

        self.status_pill.setText(tray_view.status_text)
        self.preview.setPlainText(floating_view.primary_text)
        self.helper.setText(floating_view.helper_text)
        self.enter_button.setEnabled(floating_view.can_confirm)
        self.escape_button.setEnabled(floating_view.can_cancel)
        self.copy_button.setEnabled(floating_view.can_copy)

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
