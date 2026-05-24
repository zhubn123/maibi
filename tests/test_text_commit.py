import pytest

from client.text_commit import ClipboardPasteCommitter, Win32WindowTargeter


class _FakeClipboard:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.set_calls: list[str] = []
        self.cleared = False
        self.fail_set = False
        self.fail_restore = False

    def get_text(self) -> str | None:
        return self.text

    def set_text(self, text: str) -> None:
        if self.fail_set:
            raise RuntimeError("clipboard unavailable")
        if self.fail_restore and self.set_calls:
            raise RuntimeError("restore failed")
        self.text = text
        self.set_calls.append(text)

    def clear(self) -> None:
        self.cleared = True
        self.text = None


class _FakeKeyboard:
    def __init__(self) -> None:
        self.pasted = False
        self.fail = False

    def paste(self) -> None:
        if self.fail:
            raise RuntimeError("paste failed")
        self.pasted = True


class _FakeTargeter:
    def __init__(self, handle: int | None = 42) -> None:
        self.handle = handle
        self.restored: list[int | None] = []

    def capture_foreground(self) -> int | None:
        return self.handle

    def restore_foreground(self, handle: int | None) -> None:
        self.restored.append(handle)


class _FakeWin32Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int | bool]] = []

    def GetCurrentThreadId(self) -> int:
        return 100


class _FakeWin32Con:
    SW_RESTORE = 9


class _FakeWin32Gui:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.foreground = 11

    def GetForegroundWindow(self) -> int:
        return self.foreground

    def ShowWindow(self, handle: int, command: int) -> None:
        self.calls.append(("ShowWindow", handle))

    def BringWindowToTop(self, handle: int) -> None:
        self.calls.append(("BringWindowToTop", handle))

    def SetForegroundWindow(self, handle: int) -> None:
        self.calls.append(("SetForegroundWindow", handle))

    def SetFocus(self, handle: int) -> None:
        self.calls.append(("SetFocus", handle))


class _FakeWin32Process:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, bool]] = []

    def GetWindowThreadProcessId(self, handle: int) -> tuple[int, int]:
        return (handle + 1000, 1)

    def AttachThreadInput(self, current_thread: int, target_thread: int, attach: bool) -> None:
        self.calls.append(("AttachThreadInput", current_thread, target_thread, attach))


def _committer(
    clipboard: _FakeClipboard,
    keyboard: _FakeKeyboard,
    targeter: _FakeTargeter | None = None,
) -> ClipboardPasteCommitter:
    return ClipboardPasteCommitter(
        clipboard=clipboard,
        keyboard=keyboard,
        targeter=targeter,
        restore_delay_seconds=0,
    )


def test_clipboard_paste_committer_writes_text_pastes_and_restores_original_text() -> None:
    clipboard = _FakeClipboard("原剪贴板")
    keyboard = _FakeKeyboard()
    targeter = _FakeTargeter(99)

    result = _committer(clipboard, keyboard, targeter).commit("识别文本", target_handle=99)

    assert result.ok is True
    assert keyboard.pasted is True
    assert targeter.restored == [99]
    assert clipboard.set_calls == ["识别文本", "原剪贴板"]
    assert clipboard.text == "原剪贴板"


def test_clipboard_paste_committer_clears_clipboard_when_no_original_text() -> None:
    clipboard = _FakeClipboard(None)
    keyboard = _FakeKeyboard()

    result = _committer(clipboard, keyboard).commit("识别文本")

    assert result.ok is True
    assert keyboard.pasted is True
    assert clipboard.cleared is True
    assert clipboard.text is None


def test_clipboard_paste_committer_rejects_empty_text() -> None:
    clipboard = _FakeClipboard("原剪贴板")
    keyboard = _FakeKeyboard()

    result = _committer(clipboard, keyboard).commit("")

    assert result.ok is False
    assert result.error_code == "empty_text"
    assert keyboard.pasted is False
    assert clipboard.set_calls == []


@pytest.mark.parametrize("failure", ["clipboard", "keyboard"])
def test_clipboard_paste_committer_reports_write_or_paste_failure(failure: str) -> None:
    clipboard = _FakeClipboard("原剪贴板")
    keyboard = _FakeKeyboard()
    if failure == "clipboard":
        clipboard.fail_set = True
    else:
        keyboard.fail = True

    result = _committer(clipboard, keyboard).commit("识别文本")

    assert result.ok is False
    assert result.error_code == "commit_failed"


def test_clipboard_paste_committer_restores_original_text_after_paste_failure() -> None:
    clipboard = _FakeClipboard("原剪贴板")
    keyboard = _FakeKeyboard()
    keyboard.fail = True

    result = _committer(clipboard, keyboard).commit("识别文本")

    assert result.ok is False
    assert result.error_code == "commit_failed"
    assert clipboard.text == "原剪贴板"
    assert clipboard.set_calls == ["识别文本", "原剪贴板"]


def test_clipboard_paste_committer_reports_restore_failure_after_paste() -> None:
    clipboard = _FakeClipboard("原剪贴板")
    clipboard.fail_restore = True
    keyboard = _FakeKeyboard()

    result = _committer(clipboard, keyboard).commit("识别文本")

    assert result.ok is False
    assert result.error_code == "clipboard_restore_failed"
    assert keyboard.pasted is True


def test_win32_window_targeter_restores_foreground_window_with_thread_attach() -> None:
    api = _FakeWin32Api()
    con = _FakeWin32Con()
    gui = _FakeWin32Gui()
    process = _FakeWin32Process()
    targeter = Win32WindowTargeter(api=api, con=con, gui=gui, process=process)

    targeter.restore_foreground(42)

    assert gui.calls == [
        ("ShowWindow", 42),
        ("BringWindowToTop", 42),
        ("SetForegroundWindow", 42),
        ("SetFocus", 42),
    ]
    assert process.calls == [
        ("AttachThreadInput", 100, 1011, True),
        ("AttachThreadInput", 100, 1042, True),
        ("AttachThreadInput", 100, 1042, False),
        ("AttachThreadInput", 100, 1011, False),
    ]
