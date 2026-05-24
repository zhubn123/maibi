import pytest

from client.text_commit import ClipboardPasteCommitter


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
