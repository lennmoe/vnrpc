"""The screenshot key: a global hotkey that's only registered while the game is
the window in front, so it never steals the key from other programs."""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

from .winapi import foreground_window, window_pid

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                                             wintypes.DWORD]
user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x1
QS_ALLINPUT = 0x04FF
_HOTKEY_ID = 0x5C01
_POLL_MS = 100

_MODIFIERS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_NAMED_KEYS = {
    "PrintScreen": 0x2C, "Pause": 0x13, "Insert": 0x2D, "Home": 0x24, "End": 0x23, "PageUp": 0x21,
    "PageDown": 0x22, "ScrollLock": 0x91, "Space": 0x20,
}
# Tk keysym -> our key name, for the few that differ.
_TK_KEYSYMS = {"Print": "PrintScreen", "Prior": "PageUp", "Next": "PageDown", "Scroll_Lock": "ScrollLock",
               "space": "Space"}


def _vk_for(name: str) -> int | None:
    upper = name.upper()
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(upper)
    if upper.startswith("F") and upper[1:].isdigit() and 1 <= int(upper[1:]) <= 24:
        return 0x70 + int(upper[1:]) - 1
    for key, vk in _NAMED_KEYS.items():
        if key.upper() == upper:
            return vk
    return None


def parse(text: str | None) -> tuple[int, int] | None:
    """``"Ctrl+Shift+S"`` -> ``(MOD_CONTROL | MOD_SHIFT, ord("S"))``; ``None`` for
    an empty (turned off) or unrecognised hotkey."""
    parts = [p.strip() for p in (text or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for part in parts[:-1]:
        flag = next((f for name, f in _MODIFIERS if name.lower() == part.lower()), None)
        if flag is None:
            return None
        mods |= flag
    vk = _vk_for(parts[-1])
    return (mods, vk) if vk is not None else None


def normalize(text: str | None) -> str:
    """The canonical spelling of a hotkey (``"shift+ctrl+f12"`` -> ``"Ctrl+Shift+F12"``),
    or ``""`` if it isn't one."""
    parsed = parse(text)
    if parsed is None:
        return ""
    mods, vk = parsed
    if 0x70 <= vk <= 0x87:
        key = f"F{vk - 0x6F}"
    else:
        key = next((name for name, code in _NAMED_KEYS.items() if code == vk), chr(vk))
    return "+".join([name for name, flag in _MODIFIERS if mods & flag] + [key])


_TK_STATE = (("Ctrl", 0x4), ("Alt", 0x20000), ("Shift", 0x1))  # Tk's event.state bits on Windows


def from_key_event(keysym: str, state: int) -> str | None:
    """The hotkey for a Tk key event; ``None`` for a lone modifier (the user is
    still pressing the combination)."""
    key = _TK_KEYSYMS.get(keysym, keysym)
    if _vk_for(key) is None:
        return None
    mods = [name for name, bit in _TK_STATE if state & bit]
    if any(user32.GetKeyState(vk) & 0x8000 for vk in (0x5B, 0x5C)):  # Tk doesn't report the Windows key
        mods.append("Win")
    return normalize("+".join(mods + [key]))


class HotkeyListener:
    """Calls ``on_press`` (on its own thread) when the hotkey is pressed while a
    window of process ``target_pid`` is in front. ``on_error`` gets a message when
    another program already owns the combination."""

    def __init__(self, on_press: Callable[[], None], on_error: Callable[[str], None] | None = None) -> None:
        self._on_press = on_press
        self._on_error = on_error or (lambda msg: None)
        self._hotkey = ""
        self._target_pid = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def set_hotkey(self, text: str | None) -> None:
        self._hotkey = normalize(text)

    def set_target(self, pid: int) -> None:
        self._target_pid = int(pid or 0)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        # RegisterHotKey ties the hotkey to this thread: register, receive and
        # unregister all happen here.
        registered = ""
        failed: tuple[str, int] | None = None  # reported once per hotkey and game session
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                        try:
                            self._on_press()
                        except Exception:
                            pass
                hotkey, pid = self._hotkey, self._target_pid
                wanted = hotkey if pid and window_pid(foreground_window()) == pid else ""
                if wanted != registered:
                    if registered:
                        user32.UnregisterHotKey(None, _HOTKEY_ID)
                        registered = ""
                    if wanted and (wanted, pid) != failed:
                        mods, vk = parse(wanted)
                        if user32.RegisterHotKey(None, _HOTKEY_ID, mods | MOD_NOREPEAT, vk):
                            registered, failed = wanted, None
                        else:
                            failed = (wanted, pid)
                            self._on_error(f"Screenshot key {wanted} is already used by another program "
                                           "— pick another one in Settings.")
                user32.MsgWaitForMultipleObjects(0, None, False, _POLL_MS, QS_ALLINPUT)
        finally:
            if registered:
                user32.UnregisterHotKey(None, _HOTKEY_ID)
