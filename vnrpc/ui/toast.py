from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes

import customtkinter as ctk

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

_current: "tk.Toplevel | None" = None


def show_toast(master, title: str, detail: str = "", *, image=None, ok: bool = True,
               area: tuple[int, int, int, int] | None = None, duration_ms: int = 2200) -> None:
    """A small note in the top-left corner of ``area`` (screen pixels, e.g. the
    game's window; default: the main screen) that fades out by itself. It never
    takes the focus, so the game keeps its keyboard and stays fullscreen."""
    global _current
    if _current is not None:
        try:
            _current.destroy()
        except tk.TclError:
            pass

    win = tk.Toplevel(master)
    _current = win
    win.withdraw()
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=t.resolve(t.BORDER))

    box = ctk.CTkFrame(win, fg_color=t.SURFACE, corner_radius=0)
    box.pack(padx=1, pady=1)
    if image is not None:
        ctk.CTkLabel(box, text="", image=image).pack(side="left", padx=(10, 0), pady=10)
    text = ctk.CTkFrame(box, fg_color="transparent")
    text.pack(side="left", padx=(12, 16), pady=10)
    ctk.CTkLabel(text, text=title, anchor="w", font=t.font(13, "bold"),
                 text_color=t.TEXT if ok else t.RED).pack(fill="x")
    if detail:
        t.muted(text, t.ellipsize(detail, 48), size=11).pack(fill="x")

    win.update_idletasks()
    hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
    left, top = (area[0], area[1]) if area else (0, 0)
    win.geometry(f"+{left + 16}+{top + 16}")
    win.deiconify()
    _fade(win, duration_ms)


def _fade(win: tk.Toplevel, delay_ms: int) -> None:
    def step(alpha: float) -> None:
        try:
            if alpha <= 0.05:
                win.destroy()
                return
            win.attributes("-alpha", alpha)
            win.after(30, lambda: step(alpha - 0.1))
        except tk.TclError:  # already gone
            pass

    win.after(delay_ms, lambda: step(0.95))
