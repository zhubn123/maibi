import ctypes

from client.hotkey import (
    HotkeyAction,
    HotkeyDecision,
    HotkeyEvent,
    HotkeyKey,
    HotkeyState,
    _kernel32,
    _user32,
)


def test_ctrl_alt_space_press_and_release_emit_recording_actions_once() -> None:
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
