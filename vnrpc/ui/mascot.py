"""Desktop mascot, ukagaka style: a character PNG standing on the desktop with
real per-pixel transparency, saying a word in a speech balloon when something
happens (a VN starts, a new chapter, a screenshot…). Drag it anywhere; click
it for a word, double-click opens the app, right-click for the menu."""
from __future__ import annotations

import ctypes
import random
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageChops

from ..paths import MASCOT_PNG
from . import theme as t

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
    ctypes.POINTER(wintypes.POINT), wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80000, 0x80, 0x08000000, 0x8
ULW_ALPHA, AC_SRC_ALPHA = 0x2, 0x1
SPI_GETWORKAREA = 0x30
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

_BALLOON_KEY = "#010203"  # painted see-through around the balloon's rounded corners
_DRAG_SLOP = 4
_POKES = (
    "Need something to read? Right-click me for a random pick from your wishlist!",
    "I'm keeping an eye on your reading time~",
    "Hehe, that tickles!",
)


def load_character(path: str | None, height: int) -> Image.Image:
    """The character at ``height`` pixels, transparent margins cropped. Falls back
    to the built-in one when ``path`` is empty or can't be read."""
    for candidate in (path, str(MASCOT_PNG)):
        if not candidate:
            continue
        try:
            with Image.open(candidate) as im:
                img = im.convert("RGBA")
        except (OSError, ValueError):
            continue
        box = img.getchannel("A").getbbox()
        if box:
            img = img.crop(box)
        height = max(80, min(int(height), 2000))
        return img.resize((max(1, round(img.width * height / img.height)), height), Image.LANCZOS)
    raise OSError("no character image")


def premultiplied_bgra(img: Image.Image) -> bytes:
    """What UpdateLayeredWindow wants: BGRA, colors already multiplied by alpha."""
    r, g, b, a = img.split()
    return Image.merge("RGBA", tuple(ImageChops.multiply(c, a) for c in (b, g, r)) + (a,)).tobytes()


def make_layered(win: tk.Toplevel, extra_style: int = 0) -> int:
    """Turn a (shown, borderless) Toplevel into a layered window; returns its hwnd."""
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | extra_style
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    return hwnd


def paint_layered(hwnd: int, img: Image.Image, pos: tuple[int, int], alpha: int = 255,
                  data: bytes | None = None) -> None:
    """Show ``img`` (RGBA) as the whole content of layered window ``hwnd`` at
    ``pos``, faded to ``alpha``. ``data``: its :func:`premultiplied_bgra`, if
    already computed (fading repaints the same image)."""
    w, h = img.size
    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(mem, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    try:
        data = data or premultiplied_bgra(img)
        ctypes.memmove(bits, data, len(data))
        old = gdi32.SelectObject(mem, bmp)
        blend = BLENDFUNCTION(0, 0, max(0, min(255, int(alpha))), AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(hwnd, screen, ctypes.byref(wintypes.POINT(*pos)),
                                   ctypes.byref(wintypes.SIZE(w, h)), mem, ctypes.byref(wintypes.POINT(0, 0)),
                                   0, ctypes.byref(blend), ULW_ALPHA)
        gdi32.SelectObject(mem, old)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def default_position(size: tuple[int, int]) -> tuple[int, int]:
    """Standing on the taskbar, near the right edge of the main screen."""
    _left, _top, right, bottom = work_area()
    return right - size[0] - 40, bottom - size[1]


def clamp_position(pos, size: tuple[int, int]) -> tuple[int, int] | None:
    """``pos`` if most of the character would still be on some screen, else None."""
    try:
        x, y = int(pos[0]), int(pos[1])
    except (TypeError, ValueError, IndexError):
        return None
    vx, vy = user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw, vh = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if x + size[0] // 2 < vx or x + size[0] // 2 > vx + vw or y + size[1] // 2 < vy or y > vy + vh - 40:
        return None
    return x, y


class Mascot:
    def __init__(self, master, config, *, on_open: Callable[[], None], on_pick: Callable[[], None],
                 on_hide: Callable[[], None]) -> None:
        self.config = config
        self._on_open, self._on_pick, self._on_hide = on_open, on_pick, on_hide
        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg="black")
        self._hwnd = 0
        self._img: Image.Image | None = None
        self._pos = (0, 0)
        self._press: tuple[int, int, int, int] | None = None
        self._dragged = False
        self._balloon = _Balloon(master)
        self._hide_job = None

        self.win.bind("<ButtonPress-1>", self._on_press)
        self.win.bind("<B1-Motion>", self._on_drag)
        self.win.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Double-Button-1>", lambda _e: self._on_open())
        self.win.bind("<Button-3>", self._on_menu)
        self.menu = tk.Menu(self.win, tearoff=0)
        self.menu.add_command(label="Open Visual Novel RPC", command=lambda: self._on_open())
        self.menu.add_command(label="Random VN from my wishlist", command=lambda: self._on_pick())
        self.menu.add_separator()
        self.menu.add_command(label="Hide the mascot", command=lambda: self._on_hide())
        self.reload()

    # -- drawing ---------------------------------------------------------------
    def reload(self) -> None:
        """(Re)apply the image, size and "on top" settings."""
        self._img = load_character(self.config.get("mascot_image"), self.config.get("mascot_height") or 420)
        size = self._img.size
        self._pos = clamp_position(self.config.get("mascot_pos"), size) or default_position(size)
        self.win.geometry(f"{size[0]}x{size[1]}+{self._pos[0]}+{self._pos[1]}")
        self.win.deiconify()
        self._hwnd = make_layered(self.win)
        topmost = bool(self.config.get("mascot_topmost"))
        self.win.attributes("-topmost", topmost)
        self._balloon.set_topmost(topmost)
        self._paint()

    def _paint(self) -> None:
        paint_layered(self._hwnd, self._img, self._pos)

    # -- talking ---------------------------------------------------------------
    def say(self, text: str, seconds: float = 6) -> None:
        if not self.config.get("mascot_talk", True) or not self.win.winfo_exists():
            return
        w, h = self._img.size
        self._balloon.show(text, self._pos, (w, h))
        if self._hide_job:
            self.win.after_cancel(self._hide_job)
        self._hide_job = self.win.after(int(seconds * 1000), self._balloon.hide)

    def poke(self) -> None:
        self.say(random.choice(_POKES))

    def destroy(self) -> None:
        for widget in (self._balloon.win, self.win):
            try:
                widget.destroy()
            except tk.TclError:
                pass

    # -- mouse -----------------------------------------------------------------
    def _on_press(self, event) -> None:
        self._press = (event.x_root, event.y_root, *self._pos)
        self._dragged = False

    def _on_drag(self, event) -> None:
        if not self._press:
            return
        x0, y0, wx, wy = self._press
        dx, dy = event.x_root - x0, event.y_root - y0
        if not self._dragged and abs(dx) + abs(dy) < _DRAG_SLOP:
            return
        self._dragged = True
        self._balloon.hide()
        self._pos = (wx + dx, wy + dy)
        self.win.geometry(f"+{self._pos[0]}+{self._pos[1]}")

    def _on_release(self, _event) -> None:
        if self._dragged:
            self.config["mascot_pos"] = list(self._pos)
            self.config.save()
        else:
            self.poke()
        self._press = None

    def _on_menu(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()


class _Balloon:
    """A rounded speech bubble next to the character's head that never takes the focus."""

    def __init__(self, master) -> None:
        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=_BALLOON_KEY)
        self.win.attributes("-transparentcolor", _BALLOON_KEY)
        box = ctk.CTkFrame(self.win, fg_color=t.SURFACE, border_color=t.ACCENT, border_width=2,
                           corner_radius=16, bg_color=_BALLOON_KEY)
        box.pack()
        self.label = ctk.CTkLabel(box, text="", wraplength=240, justify="left", font=t.font(13),
                                  text_color=t.TEXT)
        self.label.pack(padx=16, pady=12)
        for widget in (self.win, box, self.label):
            widget.bind("<Button-1>", lambda _e: self.hide())
        self.win.update_idletasks()
        hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def set_topmost(self, on: bool) -> None:
        self.win.attributes("-topmost", on)

    def show(self, text: str, char_pos: tuple[int, int], char_size: tuple[int, int]) -> None:
        self.label.configure(text=text)
        self.win.update_idletasks()
        bw, bh = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        cx, cy = char_pos
        cw, ch = char_size
        left, top, right, _bottom = work_area()
        # Beside the head, on whichever side has room (the left one by default).
        x = cx - bw + cw // 6
        if x < left:
            x = cx + cw - cw // 6
        x = max(left, min(x, right - bw))
        y = max(top, cy + ch // 10)
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.lift()

    def hide(self) -> None:
        try:
            self.win.withdraw()
        except tk.TclError:
            pass
