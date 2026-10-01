from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

from .winapi import foreground_window, window_pid

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
                                             wintypes.DWORD]
user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
PM_REMOVE = 0x1
QS_ALLINPUT = 0x04FF
_POLL_MS = 100
# Modifier flag -> the keys that hold it.
_MOD_KEYS = ((MOD_CONTROL, (0x11,)), (MOD_ALT, (0x12,)), (MOD_SHIFT, (0x10,)), (MOD_WIN, (0x5B, 0x5C)))

_MODIFIERS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_NAMED_KEYS = {
    "PrintScreen": 0x2C, "Pause": 0x13, "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
    "PageUp": 0x21, "PageDown": 0x22, "ScrollLock": 0x91, "Space": 0x20, "Tab": 0x09,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    **{f"Numpad{n}": 0x60 + n for n in range(10)},
    "NumpadMultiply": 0x6A, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D, "NumpadDecimal": 0x6E,
    "NumpadDivide": 0x6F,
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


def _name_for_vk(vk: int) -> str | None:
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return next((name for name, code in _NAMED_KEYS.items() if code == vk), None)


def from_key_event(keysym: str, state: int, keycode: int = 0) -> str | None:
    """The hotkey for a Tk key event; ``None`` for a lone modifier (the user is
    still pressing the combination) or a key that can't be one. On Windows Tk's
    ``keycode`` is the virtual-key code, which names keys Tk spells its own way
    (numpad, AZERTY digits…)."""
    key = _TK_KEYSYMS.get(keysym, keysym)
    if _vk_for(key) is None:
        key = _name_for_vk(keycode) if keycode else None
        if key is None:
            return None
    mods = [name for name, bit in _TK_STATE if state & bit]
    if any(user32.GetKeyState(vk) & 0x8000 for vk in (0x5B, 0x5C)):  # Tk doesn't report the Windows key
        mods.append("Win")
    return normalize("+".join(mods + [key]))


def _held_modifiers() -> int:
    return sum(flag for flag, vks in _MOD_KEYS if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks))


class HotkeyListener:
    """Calls ``on_press`` (it must return quickly) when the hotkey is pressed
    while a window of process ``target_pid`` is in front. The key is then kept
    from the game and from Windows (no Snipping Tool on Print Screen).
    ``on_error`` gets a message if the keyboard can't be watched."""

    def __init__(self, on_press: Callable[[], None], on_error: Callable[[str], None] | None = None) -> None:
        self._on_press = on_press
        self._on_error = on_error or (lambda msg: None)
        self._hotkey = ""
        self._target_pid = 0
        self._combo: tuple[int, int] | None = None  # (modifiers, vk) while the hook is in
        self._held = False  # went down as the hotkey and hasn't been released yet
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc = HOOKPROC(self._hook_proc)  # kept alive for as long as Windows may call it

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

    def _game_in_front(self) -> bool:
        pid = self._target_pid
        return bool(pid) and window_pid(foreground_window()) == pid

    def handle_key(self, msg: int, vk: int) -> bool:
        """One key event seen by the hook; True to keep it from everyone else."""
        combo = self._combo
        if combo is None or vk != combo[1]:
            return False
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if self._held:
                return True  # auto-repeat while it's held down
            if _held_modifiers() != combo[0] or not self._game_in_front():
                return False
            self._held = True
            self._press()
            return True
        if msg in (WM_KEYUP, WM_SYSKEYUP):
            if self._held:
                self._held = False
                return True
            # Some keyboards only report Print Screen when it's released.
            if _held_modifiers() == combo[0] and self._game_in_front():
                self._press()
                return True
        return False

    def _press(self) -> None:
        try:
            self._on_press()
        except Exception:
            pass

    def _hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code == 0:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if self.handle_key(w_param, info.vkCode):
                    return 1
            except Exception:
                pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _run(self) -> None:
        # Windows calls the hook on this thread, while it waits for messages below.
        hook = None
        active = None
        reported = False
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    pass
                wanted = parse(self._hotkey) if self._game_in_front() else None
                if wanted != active:
                    if hook:
                        user32.UnhookWindowsHookEx(hook)
                        hook = None
                    self._combo, self._held = None, False
                    if wanted:
                        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc,
                                                        kernel32.GetModuleHandleW(None), 0)
                        if hook:
                            self._combo = wanted
                        elif not reported:
                            reported = True
                            self._on_error("Couldn't watch the screenshot key "
                                           f"(Windows error {ctypes.get_last_error()}).")
                    active = wanted
                user32.MsgWaitForMultipleObjects(0, None, False, _POLL_MS, QS_ALLINPUT)
        finally:
            if hook:
                user32.UnhookWindowsHookEx(hook)
