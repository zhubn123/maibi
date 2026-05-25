import ctypes
import logging

from client.hotkey import (
    HotkeyAction,
    HotkeyDecision,
    HotkeyEvent,
    HotkeyKey,
    HotkeyState,
    Win32KeyboardHook,
    _kernel32,
    _user32,
)


def test_ctrl_alt_space_press_and_release_emit_recording_actions_once(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="client.hotkey")
    state = HotkeyState()

    assert state.handle(HotkeyEvent(HotkeyKey.CONTROL, True)) == HotkeyDecision()
    assert state.handle(HotkeyEvent(HotkeyKey.ALT, True)) == HotkeyDecision()
    assert state.handle(HotkeyEvent(HotkeyKey.SPACE, True)) == HotkeyDecision(
        action=HotkeyAction.START_RECORDING,
        suppress=True,
    )
    assert state.handle(HotkeyEvent(HotkeyKey.SPACE, True)) == HotkeyDecision(suppress=True)
    assert state.handle(HotkeyEvent(HotkeyKey.SPACE, False)) == HotkeyDecision(
        action=HotkeyAction.STOP_RECORDING,
        suppress=True,
    )
    assert "hotkey event key=space state=down" in caplog.text
    assert "action=start_recording suppress=True" in caplog.text
    assert "action=stop_recording suppress=True" in caplog.text


def test_releasing_modifier_also_stops_recording() -> None:
    state = HotkeyState()

    state.handle(HotkeyEvent(HotkeyKey.CONTROL, True))
    state.handle(HotkeyEvent(HotkeyKey.ALT, True))
    state.handle(HotkeyEvent(HotkeyKey.SPACE, True))

    assert state.handle(HotkeyEvent(HotkeyKey.ALT, False)) == HotkeyDecision(
        action=HotkeyAction.STOP_RECORDING,
        suppress=False,
    )


def test_enter_and_escape_only_emit_when_active() -> None:
    active = False
    state = HotkeyState(active_getter=lambda: active)

    assert state.handle(HotkeyEvent(HotkeyKey.ENTER, True)) == HotkeyDecision()
    assert state.handle(HotkeyEvent(HotkeyKey.ENTER, False)) == HotkeyDecision()
    active = True
    assert state.handle(HotkeyEvent(HotkeyKey.ENTER, True)) == HotkeyDecision(suppress=True)
    assert state.handle(HotkeyEvent(HotkeyKey.ENTER, False)) == HotkeyDecision(
        action=HotkeyAction.CONFIRM,
        suppress=True,
    )
    assert state.handle(HotkeyEvent(HotkeyKey.ESCAPE, True)) == HotkeyDecision(suppress=True)
    assert state.handle(HotkeyEvent(HotkeyKey.ESCAPE, False)) == HotkeyDecision(
        action=HotkeyAction.CANCEL,
        suppress=True,
    )


def test_win32_api_prototypes_are_configured_for_hook_calls() -> None:
    user32 = _user32()
    kernel32 = _kernel32()

    assert len(user32.SetWindowsHookExW.argtypes) == 4
    assert len(user32.CallNextHookEx.argtypes) == 4
    assert len(user32.GetMessageW.argtypes) == 4
    assert user32.DispatchMessageW.restype == ctypes.c_ssize_t
    assert kernel32.GetCurrentThreadId.restype is not None


def test_win32_keyboard_hook_raises_when_hook_install_fails(monkeypatch) -> None:
    class _FakeUser32:
        def SetWindowsHookExW(self, *_args):
            return None

    class _FakeKernel32:
        def GetCurrentThreadId(self):
            return 123

        def GetModuleHandleW(self, _name):
            return None

    monkeypatch.setattr("client.hotkey._user32", lambda: _FakeUser32())
    monkeypatch.setattr("client.hotkey._kernel32", lambda: _FakeKernel32())
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)

    listener = Win32KeyboardHook(
        state=HotkeyState(),
        on_action=lambda _action: None,
    )

    listener._run()

    assert listener._start_error is not None
    assert str(listener._start_error) == "global_hotkey_hook_failed:5"
