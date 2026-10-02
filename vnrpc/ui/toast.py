from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes

import customtkinter as ctk
from PIL import Image

from . import theme as t

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetParent.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long

GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000

_current: list = []  # the windows of the note on screen
_BUBBLE_KEY = "#010203"  # painted see-through around the bubble's rounded corners


def show_toast(master, title: str, detail: str = "", *, image=None, ok: bool = True,
               area: tuple[int, int, int, int] | None = None, duration_ms: int = 2200,
               sprite: "Image.Image | None" = None) -> None:
    """A small note in the top-left corner of ``area`` (screen pixels, e.g. the
    game's window; default: the main screen) that fades out by itself. It never
    takes the focus, so the game keeps its keyboard and stays fullscreen.
    With ``sprite`` (an RGBA character image), the character stands there and
    the note is its speech bubble."""
    for old in _current:
        try:
            old.destroy()
        except tk.TclError:
            pass
    _current.clear()

    win = tk.Toplevel(master)
    _current.append(win)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    if sprite is None:
        win.configure(bg=t.resolve(t.BORDER))
        box = ctk.CTkFrame(win, fg_color=t.SURFACE, corner_radius=0)
        box.pack(padx=1, pady=1)
    else:
        win.configure(bg=_BUBBLE_KEY)
        win.attributes("-transparentcolor", _BUBBLE_KEY)
        box = ctk.CTkFrame(win, fg_color=t.SURFACE, corner_radius=16, border_width=2,
                           border_color=t.ACCENT if ok else t.RED, bg_color=_BUBBLE_KEY)
        box.pack()
    if image is not None:
        ctk.CTkLabel(box, text="", image=image).pack(side="left", padx=(12, 0), pady=12)
    text = ctk.CTkFrame(box, fg_color="transparent")
    text.pack(side="left", padx=(12, 16), pady=12)
    ctk.CTkLabel(text, text=title, anchor="w", font=t.font(13, "bold"),
                 text_color=t.TEXT if ok else t.RED).pack(fill="x")
    if detail:
        t.muted(text, t.ellipsize(detail, 48), size=11).pack(fill="x")

    win.update_idletasks()
    _no_focus(win)
    left, top = (area[0] + 16, area[1] + 16) if area else (16, 16)
    fade = [lambda alpha: win.attributes("-alpha", alpha)]
    if sprite is not None:
        fade.append(_show_sprite(master, sprite, (left, top)))
        # The bubble beside the character's head, its edge tucked behind the figure.
        left += max(0, sprite.width - 10)
        top += sprite.height // 8
    win.geometry(f"+{left}+{top}")
    win.deiconify()
    _fade(win, duration_ms, fade)


def _show_sprite(master, sprite, pos: tuple[int, int]):
    """The character in its own see-through window; returns how to fade it."""
    from .mascot import WS_EX_NOACTIVATE as NOACTIVATE, make_layered, paint_layered, premultiplied_bgra

    char = tk.Toplevel(master)
    _current.append(char)
    char.overrideredirect(True)
    char.attributes("-topmost", True)
    char.geometry(f"{sprite.width}x{sprite.height}+{pos[0]}+{pos[1]}")
    hwnd = make_layered(char, NOACTIVATE | WS_EX_TOPMOST)
    data = premultiplied_bgra(sprite)
    paint_layered(hwnd, sprite, pos, data=data)
    return lambda alpha: paint_layered(hwnd, sprite, pos, int(alpha * 255), data=data)


def _no_focus(win: tk.Toplevel) -> None:
    hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def _fade(win: tk.Toplevel, delay_ms: int, setters) -> None:
    windows = list(_current)

    def step(alpha: float) -> None:
        try:
            if alpha <= 0.05:
                for w in windows:
                    w.destroy()
                return
            for set_alpha in setters:
                set_alpha(alpha)
            win.after(30, lambda: step(alpha - 0.1))
        except tk.TclError:  # already gone
            pass

    win.after(delay_ms, lambda: step(0.95))
