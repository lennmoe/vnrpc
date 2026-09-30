"""Only one copy of the app runs at a time: starting it again just brings the
running one to the front (out of the tray if it's hidden there)."""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.SetEvent.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_user32.AllowSetForegroundWindow.restype = wintypes.BOOL

ERROR_ALREADY_EXISTS = 183
ASFW_ANY = 0xFFFFFFFF
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0

# "Local\": one app per Windows session (another user logged in keeps their own).
_MUTEX = "Local\\VisualNovelRPC.Instance"
_SHOW_EVENT = "Local\\VisualNovelRPC.Show"


class Instance:
    """Held by the running copy for its whole life (the mutex goes with the process)."""

    def __init__(self, mutex: int, show_event: int) -> None:
        self._mutex = mutex
        self._show_event = show_event

    def on_show_request(self, callback: Callable[[], None]) -> None:
        """Call ``callback`` (on a background thread) each time the app is started again."""
        def wait() -> None:
            while _kernel32.WaitForSingleObject(self._show_event, INFINITE) == WAIT_OBJECT_0:
                try:
                    callback()
                except Exception:
                    pass

        threading.Thread(target=wait, name="single-instance", daemon=True).start()


def acquire(name: str = _MUTEX, show_event: str = _SHOW_EVENT) -> Instance | None:
    """This process's claim to be *the* app. ``None`` if a copy is already running,
    in which case it has been asked to show itself and this one should just exit."""
    mutex = _kernel32.CreateMutexW(None, False, name)
    already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    # Auto-reset: one signal wakes the running copy once.
    event = _kernel32.CreateEventW(None, False, False, show_event)
    if not already or not mutex:
        return Instance(mutex, event)
    _user32.AllowSetForegroundWindow(ASFW_ANY)  # we were just started by the user: pass that on
    if event:
        _kernel32.SetEvent(event)
        _kernel32.CloseHandle(event)
    _kernel32.CloseHandle(mutex)
    return None
