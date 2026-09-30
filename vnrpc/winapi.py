from __future__ import annotations

import ctypes
import io
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_EnumWindows = user32.EnumWindows
_EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
_EnumWindows.restype = wintypes.BOOL

_GetWindowTextLengthW = user32.GetWindowTextLengthW
_GetWindowTextLengthW.argtypes = [wintypes.HWND]
_GetWindowTextLengthW.restype = ctypes.c_int

_GetWindowTextW = user32.GetWindowTextW
_GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetWindowTextW.restype = ctypes.c_int

_IsWindowVisible = user32.IsWindowVisible
_IsWindowVisible.argtypes = [wintypes.HWND]
_IsWindowVisible.restype = wintypes.BOOL

_IsWindow = user32.IsWindow
_IsWindow.argtypes = [wintypes.HWND]
_IsWindow.restype = wintypes.BOOL

_GetWindow = user32.GetWindow
_GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_GetWindow.restype = wintypes.HWND

_GetWindowLongW = user32.GetWindowLongW
_GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLongW.restype = ctypes.c_long

_GetClassNameW = user32.GetClassNameW
_GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_GetClassNameW.restype = ctypes.c_int

_GetWindowThreadProcessId = user32.GetWindowThreadProcessId
_GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_GetWindowThreadProcessId.restype = wintypes.DWORD

_GetForegroundWindow = user32.GetForegroundWindow
_GetForegroundWindow.restype = wintypes.HWND

_OpenProcess = kernel32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE

_CloseHandle = kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL

_QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
_QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_QueryFullProcessImageNameW.restype = wintypes.BOOL

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    exe_path: str
    class_name: str

    @property
    def exe(self) -> str:
        return self.exe_path.rsplit("\\", 1)[-1] if self.exe_path else ""


def _window_title(hwnd: int) -> str:
    length = _GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_image_path(pid: int) -> str:
    handle = _OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if _QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _CloseHandle(handle)


def _pid_for_window(hwnd: int) -> int:
    pid = wintypes.DWORD()
    _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def is_window(hwnd: int) -> bool:
    return bool(_IsWindow(hwnd))


def is_window_visible(hwnd: int) -> bool:
    """False once a window is hidden -- which many engines do on exit, long before
    the window (or the process) is actually gone. Minimized windows still count."""
    return bool(_IsWindow(hwnd)) and bool(_IsWindowVisible(hwnd))


def get_window_title(hwnd: int) -> str:
    return _window_title(hwnd)


def foreground_window() -> int:
    return _GetForegroundWindow()


def list_top_level_windows(include_toolwindows: bool = False) -> list[WindowInfo]:
    """Return visible, top-level, titled windows (roughly the Alt-Tab set)."""
    results: list[WindowInfo] = []
    seen: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if not _IsWindowVisible(hwnd):
            return True
        if _GetWindow(hwnd, GW_OWNER):
            return True
        if not include_toolwindows:
            ex_style = _GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
        title = _window_title(hwnd)
        if not title.strip():
            return True
        if hwnd in seen:
            return True
        seen.add(hwnd)
        pid = _pid_for_window(hwnd)
        results.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=title,
                pid=pid,
                exe_path=_process_image_path(pid),
                class_name=_class_name(hwnd),
            )
        )
        return True

    _EnumWindows(_cb, 0)
    return results


def window_pid(hwnd: int) -> int:
    return _pid_for_window(hwnd) if hwnd else 0


gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


def _declare(dll, name: str, args: list, res) -> None:
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, res


_declare(user32, "GetWindowRect", [wintypes.HWND, ctypes.POINTER(RECT)], wintypes.BOOL)
_declare(user32, "GetClientRect", [wintypes.HWND, ctypes.POINTER(RECT)], wintypes.BOOL)
_declare(user32, "ClientToScreen", [wintypes.HWND, ctypes.POINTER(POINT)], wintypes.BOOL)
_declare(user32, "IsIconic", [wintypes.HWND], wintypes.BOOL)
_declare(user32, "GetDC", [wintypes.HWND], wintypes.HDC)
_declare(user32, "ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int)
_declare(user32, "PrintWindow", [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL)
_declare(gdi32, "CreateCompatibleDC", [wintypes.HDC], wintypes.HDC)
_declare(gdi32, "CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP)
_declare(gdi32, "SelectObject", [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ)
_declare(gdi32, "DeleteObject", [wintypes.HGDIOBJ], wintypes.BOOL)
_declare(gdi32, "DeleteDC", [wintypes.HDC], wintypes.BOOL)
_declare(gdi32, "GetDIBits", [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                              ctypes.c_void_p, wintypes.UINT], ctypes.c_int)

PW_RENDERFULLCONTENT = 0x2  # Windows 8.1+: also grabs DirectX / OpenGL content


class CaptureError(Exception):
    """Why a window couldn't be captured, in words fit for the user."""


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int]:
    """``(left, top, right, bottom)`` of the window's content area, in screen pixels."""
    rect, origin = RECT(), POINT(0, 0)
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom


def capture_window(hwnd: int):
    """The content area (no title bar or borders) of ``hwnd`` as a PIL RGB image.

    Asks the window to draw itself (works when it's covered or on another screen),
    and falls back to copying the screen when that comes back black, which some
    fullscreen games do."""
    from PIL import ImageGrab

    if not hwnd or not _IsWindow(hwnd):
        raise CaptureError("The game's window is gone.")
    if user32.IsIconic(hwnd):
        raise CaptureError("The game is minimized.")
    client = client_rect_on_screen(hwnd)
    left, top, right, bottom = client
    if right - left < 2 or bottom - top < 2:
        raise CaptureError("The game's window has no visible content.")

    img = _print_window(hwnd, client)
    if img is None or not img.getbbox():
        try:
            img = ImageGrab.grab(bbox=client, all_screens=True)
        except OSError as exc:
            raise CaptureError(f"Windows refused the capture ({exc}).") from None
    return img.convert("RGB")


def _print_window(hwnd: int, client: tuple[int, int, int, int]):
    from PIL import Image

    win = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win)):
        return None
    w, h = win.right - win.left, win.bottom - win.top
    if w <= 0 or h <= 0:
        return None
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    old = gdi32.SelectObject(mem_dc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT):
            return None
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h,
                                  biPlanes=1, biBitCount=32, biCompression=0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(header), 0):
            return None
        img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
    left, top, right, bottom = client
    return img.crop((left - win.left, top - win.top, right - win.left, bottom - win.top))


_declare(user32, "OpenClipboard", [wintypes.HWND], wintypes.BOOL)
_declare(user32, "CloseClipboard", [], wintypes.BOOL)
_declare(user32, "EmptyClipboard", [], wintypes.BOOL)
_declare(user32, "SetClipboardData", [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE)
_declare(user32, "RegisterClipboardFormatW", [wintypes.LPCWSTR], wintypes.UINT)
_declare(kernel32, "GlobalAlloc", [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL)
_declare(kernel32, "GlobalLock", [wintypes.HGLOBAL], ctypes.c_void_p)
_declare(kernel32, "GlobalUnlock", [wintypes.HGLOBAL], wintypes.BOOL)
_declare(kernel32, "GlobalFree", [wintypes.HGLOBAL], wintypes.HGLOBAL)

CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def copy_image_to_clipboard(img) -> None:
    """Put ``img`` on the clipboard as a bitmap and as PNG (Discord, browsers and
    Office read the PNG; Paint and older apps the bitmap). Raises OSError."""
    rgb = img.convert("RGB")
    bmp, png = io.BytesIO(), io.BytesIO()
    rgb.save(bmp, "BMP")
    rgb.save(png, "PNG")
    payloads = [(CF_DIB, bmp.getvalue()[14:]),  # a DIB is a .bmp minus its file header
                (user32.RegisterClipboardFormatW("PNG"), png.getvalue())]

    for _attempt in range(10):  # another app may be holding the clipboard for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise OSError("the clipboard is busy")
    try:
        user32.EmptyClipboard()
        for fmt, data in payloads:
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            ptr = kernel32.GlobalLock(handle) if handle else None
            if not ptr:
                raise OSError("out of memory")
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(fmt, handle):  # on success the clipboard owns it
                kernel32.GlobalFree(handle)
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        user32.CloseClipboard()


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.WORD), ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


_declare(shell32, "SHFileOperationW", [ctypes.POINTER(_SHFILEOPSTRUCTW)], ctypes.c_int)


def send_to_recycle_bin(path: str) -> None:
    """Delete ``path`` so it can still be restored from the Recycle Bin. Raises OSError."""
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    op = _SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom=os.path.abspath(path) + "\0",  # list ends with "\0\0"
                          fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI)
    code = shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted:
        raise OSError(f"couldn't move it to the Recycle Bin (error {code})")


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


_FOLDERID_PICTURES = _GUID(0x33E28130, 0x4E1E, 0x4676, (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xBC, 0x3B))
_declare(shell32, "SHGetKnownFolderPath",
         [ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long)
_declare(ole32, "CoTaskMemFree", [ctypes.c_void_p], None)


def pictures_folder() -> str:
    """The user's Pictures folder (wherever it's been moved to, e.g. OneDrive)."""
    ptr = ctypes.c_void_p()
    try:
        if shell32.SHGetKnownFolderPath(ctypes.byref(_FOLDERID_PICTURES), 0, None, ctypes.byref(ptr)) == 0:
            path = ctypes.wstring_at(ptr.value)
            if path:
                return path
    except OSError:
        pass
    finally:
        if ptr.value:
            ole32.CoTaskMemFree(ptr)
    return os.path.join(os.path.expanduser("~"), "Pictures")
