from __future__ import annotations

import time
from typing import Protocol

from core import CommitResult, CommitStatus


class TextClipboard(Protocol):
    def get_text(self) -> str | None: ...
    def set_text(self, text: str) -> None: ...
    def clear(self) -> None: ...


class PasteKeyboard(Protocol):
    def paste(self) -> None: ...


class WindowTargeter(Protocol):
    def capture_foreground(self) -> int | None: ...
    def restore_foreground(self, handle: int | None) -> None: ...


class ClipboardPasteCommitter:
    def __init__(
        self,
        clipboard: TextClipboard,
        keyboard: PasteKeyboard,
        targeter: WindowTargeter | None = None,
        *,
        restore_delay_seconds: float = 0.05,
    ) -> None:
        self.clipboard = clipboard
        self.keyboard = keyboard
        self.targeter = targeter
        self.restore_delay_seconds = restore_delay_seconds

    def commit(self, text: str, target_handle: int | None = None) -> CommitResult:
        if not text:
            return CommitResult(
                status=CommitStatus.FAILED,
                error_code="empty_text",
                message="没有可上屏的文本",
            )

        clipboard_changed = False
        try:
            original_text = self.clipboard.get_text()
            self.clipboard.set_text(text)
            clipboard_changed = True
            if self.targeter is not None:
                self.targeter.restore_foreground(target_handle)
            self.keyboard.paste()
        except Exception as exc:
            if clipboard_changed:
                self._restore_clipboard(original_text)
            return CommitResult(
                status=CommitStatus.FAILED,
                error_code="commit_failed",
                message=str(exc) or "文本上屏失败，请手动复制",
            )

        if self.restore_delay_seconds > 0:
            time.sleep(self.restore_delay_seconds)

        restore_error = self._restore_clipboard(original_text)
        if restore_error is not None:
            return restore_error

        return CommitResult(status=CommitStatus.SUCCESS)

    def _restore_clipboard(self, original_text: str | None) -> CommitResult | None:
        try:
            if original_text is None:
                self.clipboard.clear()
            else:
                self.clipboard.set_text(original_text)
        except Exception as exc:
            return CommitResult(
                status=CommitStatus.FAILED,
                error_code="clipboard_restore_failed",
                message=str(exc) or "文本可能已上屏，但剪贴板恢复失败",
            )
        return None


class Win32TextClipboard:
    def __init__(self) -> None:
        import win32clipboard
        import win32con

        self._clipboard = win32clipboard
        self._con = win32con

    def get_text(self) -> str | None:
        self._clipboard.OpenClipboard()
        try:
            if not self._clipboard.IsClipboardFormatAvailable(self._con.CF_UNICODETEXT):
                return None
            data = self._clipboard.GetClipboardData(self._con.CF_UNICODETEXT)
            return str(data)
        finally:
            self._clipboard.CloseClipboard()

    def set_text(self, text: str) -> None:
        self._clipboard.OpenClipboard()
        try:
            self._clipboard.EmptyClipboard()
            self._clipboard.SetClipboardData(self._con.CF_UNICODETEXT, text)
        finally:
            self._clipboard.CloseClipboard()

    def clear(self) -> None:
        self._clipboard.OpenClipboard()
        try:
            self._clipboard.EmptyClipboard()
        finally:
            self._clipboard.CloseClipboard()


class Win32PasteKeyboard:
    def __init__(self) -> None:
        import win32api
        import win32con

        self._api = win32api
        self._con = win32con

    def paste(self) -> None:
        vk_control = self._con.VK_CONTROL
        vk_v = ord("V")
        self._api.keybd_event(vk_control, 0, 0, 0)
        self._api.keybd_event(vk_v, 0, 0, 0)
        self._api.keybd_event(vk_v, 0, self._con.KEYEVENTF_KEYUP, 0)
        self._api.keybd_event(vk_control, 0, self._con.KEYEVENTF_KEYUP, 0)


class Win32WindowTargeter:
    def __init__(self) -> None:
        import win32gui

        self._gui = win32gui

    def capture_foreground(self) -> int | None:
        handle = self._gui.GetForegroundWindow()
        return int(handle) if handle else None

    def restore_foreground(self, handle: int | None) -> None:
        if handle:
            self._gui.SetForegroundWindow(handle)


def create_default_text_committer() -> ClipboardPasteCommitter:
    return ClipboardPasteCommitter(
        clipboard=Win32TextClipboard(),
        keyboard=Win32PasteKeyboard(),
        targeter=Win32WindowTargeter(),
    )
