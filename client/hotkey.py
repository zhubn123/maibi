from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from ctypes import wintypes


LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LOGGER = logging.getLogger(__name__)


class HotkeyAction(StrEnum):
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    CONFIRM = "confirm"
    CANCEL = "cancel"


class HotkeyKey(StrEnum):
    CONTROL = "control"
    ALT = "alt"
    SPACE = "space"
    ENTER = "enter"
    ESCAPE = "escape"


@dataclass(frozen=True, slots=True)
class HotkeyEvent:
    key: HotkeyKey
    pressed: bool


@dataclass(frozen=True, slots=True)
class HotkeyDecision:
    action: HotkeyAction | None = None
    suppress: bool = False


class HotkeyState:
    def __init__(self, *, active_getter: Callable[[], bool] | None = None) -> None:
        self.active_getter = active_getter or (lambda: False)
        self._pressed_keys: set[HotkeyKey] = set()
        self._recording_hotkey_down = False

    def handle(self, event: HotkeyEvent) -> HotkeyDecision:
        if event.pressed:
            self._pressed_keys.add(event.key)
            decision = self._handle_pressed(event.key)
        else:
            self._pressed_keys.discard(event.key)
            decision = self._handle_released(event.key)

        LOGGER.debug(
            "hotkey event key=%s state=%s pressed_keys=%s recording_hotkey_down=%s action=%s suppress=%s",
            event.key.value,
            "down" if event.pressed else "up",
            _format_pressed_keys(self._pressed_keys),
            self._recording_hotkey_down,
            decision.action.value if decision.action is not None else "-",
            decision.suppress,
        )
        return decision

    def _handle_pressed(self, key: HotkeyKey) -> HotkeyDecision:
        if key in {HotkeyKey.ENTER, HotkeyKey.ESCAPE} and self.active_getter():
            return HotkeyDecision(suppress=True)
        if (
            key == HotkeyKey.SPACE
            and HotkeyKey.CONTROL in self._pressed_keys
            and HotkeyKey.ALT in self._pressed_keys
            and not self._recording_hotkey_down
        ):
            self._recording_hotkey_down = True
            return HotkeyDecision(action=HotkeyAction.START_RECORDING, suppress=True)
        if key == HotkeyKey.SPACE and self._recording_hotkey_down:
            return HotkeyDecision(suppress=True)
        return HotkeyDecision()

    def _handle_released(self, key: HotkeyKey) -> HotkeyDecision:
        if key == HotkeyKey.ENTER and self.active_getter():
            return HotkeyDecision(action=HotkeyAction.CONFIRM, suppress=True)
        if key == HotkeyKey.ESCAPE and self.active_getter():
            return HotkeyDecision(action=HotkeyAction.CANCEL, suppress=True)
        if key == HotkeyKey.SPACE and self._recording_hotkey_down:
            self._recording_hotkey_down = False
            return HotkeyDecision(action=HotkeyAction.STOP_RECORDING, suppress=True)
        if key in {HotkeyKey.CONTROL, HotkeyKey.ALT} and self._recording_hotkey_down:
            self._recording_hotkey_down = False
            return HotkeyDecision(action=HotkeyAction.STOP_RECORDING, suppress=False)
        return HotkeyDecision()


class GlobalHotkeyListener:
    def start(self) -> None: ...
    def stop(self) -> None: ...


class Win32KeyboardHook:
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_QUIT = 0x0012

    VK_CONTROL = 0x11
    VK_LCONTROL = 0xA2
    VK_RCONTROL = 0xA3
    VK_MENU = 0x12
    VK_LMENU = 0xA4
    VK_RMENU = 0xA5
    VK_SPACE = 0x20
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B

    def __init__(
        self,
        *,
        state: HotkeyState,
        on_action: Callable[[HotkeyAction], None],
    ) -> None:
        self.state = state
        self.on_action = on_action
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook_handle = None
        self._callback = None
        self._ready = threading.Event()
        self._start_error: RuntimeError | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            LOGGER.info("hotkey hook start skipped because hook thread is already running")
            return
        LOGGER.info("hotkey hook starting")
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run, name="maibi-hotkey-hook", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.0)
        if self._start_error is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
            LOGGER.error("hotkey hook failed to start: %s", self._start_error)
            raise self._start_error
        LOGGER.info("hotkey hook ready thread_id=%s", self._thread_id)

    def run_forever(self) -> None:
        if self._hook_handle:
            LOGGER.info("hotkey hook run_forever skipped because hook is already installed")
            return
        LOGGER.info("hotkey hook run_forever starting on current thread")
        self._start_error = None
        self._run()
        if self._start_error is not None:
            LOGGER.error("hotkey hook run_forever failed: %s", self._start_error)
            raise self._start_error

    def stop(self) -> None:
        LOGGER.info("hotkey hook stopping thread_id=%s", self._thread_id)
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._thread_id = None
        LOGGER.info("hotkey hook stopped")

    def _run(self) -> None:
        user32 = _user32()
        kernel32 = _kernel32()
        self._thread_id = kernel32.GetCurrentThreadId()

        low_level_keyboard_proc = ctypes.WINFUNCTYPE(
            LRESULT,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def callback(code: int, wparam: int, lparam: int) -> int:
            if code >= 0:
                event = self._event_from_message(wparam, lparam)
                if event is not None:
                    decision = self.state.handle(event)
                    if decision.action is not None:
                        self.on_action(decision.action)
                    if decision.suppress:
                        return 1
            return user32.CallNextHookEx(self._hook_handle, code, wparam, lparam)

        self._callback = low_level_keyboard_proc(callback)
        self._hook_handle = user32.SetWindowsHookExW(
            self.WH_KEYBOARD_LL,
            self._callback,
            kernel32.GetModuleHandleW(None),
            0,
        )
        if not self._hook_handle:
            error_code = ctypes.get_last_error()
            self._start_error = RuntimeError(f"global_hotkey_hook_failed:{error_code}")
            self._ready.set()
            return
        LOGGER.info("hotkey hook installed thread_id=%s", self._thread_id)
        self._ready.set()

        msg = _MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
            LOGGER.info("hotkey hook uninstalled thread_id=%s", self._thread_id)

    def _event_from_message(self, wparam: int, lparam: int) -> HotkeyEvent | None:
        keyboard = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
        key = _key_from_vk(keyboard.vkCode)
        if key is None:
            return None
        if wparam in {self.WM_KEYDOWN, self.WM_SYSKEYDOWN}:
            return HotkeyEvent(key=key, pressed=True)
        if wparam in {self.WM_KEYUP, self.WM_SYSKEYUP}:
            return HotkeyEvent(key=key, pressed=False)
        return None


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", _POINT),
    ]


def _key_from_vk(vk_code: int) -> HotkeyKey | None:
    key_map = {
        Win32KeyboardHook.VK_CONTROL: HotkeyKey.CONTROL,
        Win32KeyboardHook.VK_LCONTROL: HotkeyKey.CONTROL,
        Win32KeyboardHook.VK_RCONTROL: HotkeyKey.CONTROL,
        Win32KeyboardHook.VK_MENU: HotkeyKey.ALT,
        Win32KeyboardHook.VK_LMENU: HotkeyKey.ALT,
        Win32KeyboardHook.VK_RMENU: HotkeyKey.ALT,
        Win32KeyboardHook.VK_SPACE: HotkeyKey.SPACE,
        Win32KeyboardHook.VK_RETURN: HotkeyKey.ENTER,
        Win32KeyboardHook.VK_ESCAPE: HotkeyKey.ESCAPE,
    }
    return key_map.get(vk_code)


def _format_pressed_keys(keys: set[HotkeyKey]) -> str:
    if not keys:
        return "-"
    return "+".join(sorted(key.value for key in keys))


def create_default_hotkey_listener(
    *,
    active_getter: Callable[[], bool],
    on_action: Callable[[HotkeyAction], None],
) -> GlobalHotkeyListener:
    return Win32KeyboardHook(
        state=HotkeyState(active_getter=active_getter),
        on_action=on_action,
    )


_USER32 = None
_KERNEL32 = None


def _user32():
    global _USER32
    if _USER32 is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(_MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
        user32.DispatchMessageW.restype = LRESULT
        user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        _USER32 = user32
    return _USER32


def _kernel32():
    global _KERNEL32
    if _KERNEL32 is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        _KERNEL32 = kernel32
    return _KERNEL32
