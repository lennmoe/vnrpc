from __future__ import annotations

import colorsys
import tkinter as tk
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageChops, ImageTk

from . import theme as t

SQUARE = (380, 210)  # saturation (x) / brightness (y) field
PREVIEW_W = 150
HUE_H = 14
_KNOB = 8


class ColorPicker(ctk.CTkToplevel):
    """Pick a color: a saturation/brightness square, a hue bar and an editable HEX
    field. ``on_pick`` gets ``"#RRGGBB"`` when the user confirms."""

    def __init__(self, master, color: str, on_pick: Callable[[str], None], *, title: str = "Pick a color") -> None:
        super().__init__(master)
        self._on_pick = on_pick
        width = PREVIEW_W + SQUARE[0] + 3 * 16
        t.setup_window(self, title=title, geometry=f"{width}x{SQUARE[1] + 190}", resizable=False,
                       modal_for=master)
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Return>", lambda _e: self._use())

        start = t.normalize_hex(color) or t.ACCENT
        r, g, b = (int(start[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self._square_img = self._hue_img = None

        box = t.card(self)
        box.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(box, text=title, font=t.font(15, "bold"), text_color=t.TEXT, anchor="w").pack(
            fill="x", padx=16, pady=(12, 8))

        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=16)
        self.preview = tk.Frame(top, width=PREVIEW_W, height=SQUARE[1], highlightthickness=0, bd=0)
        self.preview.pack(side="left")
        self.square = tk.Canvas(top, width=SQUARE[0], height=SQUARE[1], highlightthickness=0, bd=0,
                                cursor="crosshair", bg=t.resolve(t.SURFACE))
        self.square.pack(side="left", padx=(16, 0))
        for seq in ("<Button-1>", "<B1-Motion>"):
            self.square.bind(seq, self._on_square)

        hue_w = PREVIEW_W + 16 + SQUARE[0]
        self.hue = tk.Canvas(box, width=hue_w, height=HUE_H + 2 * _KNOB, highlightthickness=0, bd=0,
                             cursor="hand2", bg=t.resolve(t.SURFACE))
        self.hue.pack(padx=16, pady=(14, 6))
        for seq in ("<Button-1>", "<B1-Motion>"):
            self.hue.bind(seq, self._on_hue)
        self._draw_hue_bar(hue_w)

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 14))
        t.overline(row, "Hex").pack(side="left", padx=(0, 10))
        self.hex = t.entry(row, width=130, height=32, justify="center", font=t.mono(13))
        self.hex.pack(side="left")
        self.hex.bind("<KeyRelease>", self._on_hex_typed)
        self.copy_btn = t.secondary_button(row, "Copy", self._copy, width=64, height=32)
        self.copy_btn.pack(side="left", padx=8)
        t.primary_button(row, "Use color", self._use, width=100, height=32).pack(side="right")
        t.secondary_button(row, "Cancel", self._close, width=80, height=32).pack(side="right", padx=8)

        self._render(update_hex=True)

    @property
    def color(self) -> str:
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))

    def _render(self, *, update_hex: bool, redraw_square: bool = True) -> None:
        if redraw_square:
            self._draw_square()
        self._draw_markers()
        self.preview.configure(bg=self.color)
        if update_hex:
            self.hex.delete(0, tk.END)
            self.hex.insert(0, self.color)

    def _draw_square(self) -> None:
        w, h = SQUARE
        hue = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(self.h, 1, 1))
        across = Image.linear_gradient("L").rotate(90).resize((w, h))  # white → hue, left to right
        down = ImageChops.invert(Image.linear_gradient("L")).resize((w, h))  # bright → black, top to bottom
        sat = Image.composite(Image.new("RGB", (w, h), hue), Image.new("RGB", (w, h), "white"), across)
        img = Image.composite(sat, Image.new("RGB", (w, h), "black"), down)
        self._square_img = ImageTk.PhotoImage(img)
        self.square.delete("field")
        self.square.create_image(0, 0, image=self._square_img, anchor="nw", tags="field")
        self.square.tag_lower("field")

    def _draw_hue_bar(self, width: int) -> None:
        strip = Image.new("RGB", (width, 1))
        strip.putdata([tuple(round(c * 255) for c in colorsys.hsv_to_rgb(x / (width - 1), 1, 1))
                       for x in range(width)])
        self._hue_img = ImageTk.PhotoImage(strip.resize((width, HUE_H)))
        self.hue.create_image(0, _KNOB, image=self._hue_img, anchor="nw")

    def _draw_markers(self) -> None:
        x, y = self.s * (SQUARE[0] - 1), (1 - self.v) * (SQUARE[1] - 1)
        self.square.delete("knob")
        self.square.create_oval(x - _KNOB - 1, y - _KNOB - 1, x + _KNOB + 1, y + _KNOB + 1,
                                outline="#000000", width=1, tags="knob")
        self.square.create_oval(x - _KNOB, y - _KNOB, x + _KNOB, y + _KNOB, outline="#FFFFFF", width=2, tags="knob")

        width = int(self.hue.cget("width"))
        hx = min(max(_KNOB, self.h * (width - 1)), width - 1 - _KNOB)
        cy = _KNOB + HUE_H / 2
        pure = "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in colorsys.hsv_to_rgb(self.h, 1, 1)))
        self.hue.delete("knob")
        self.hue.create_oval(hx - _KNOB - 1, cy - _KNOB - 1, hx + _KNOB + 1, cy + _KNOB + 1,
                             outline="#000000", width=1, tags="knob")
        self.hue.create_oval(hx - _KNOB, cy - _KNOB, hx + _KNOB, cy + _KNOB, fill=pure, outline="#FFFFFF",
                             width=2, tags="knob")

    def _on_square(self, event) -> None:
        self.s = min(max(event.x / (SQUARE[0] - 1), 0.0), 1.0)
        self.v = 1 - min(max(event.y / (SQUARE[1] - 1), 0.0), 1.0)
        self._render(update_hex=True, redraw_square=False)

    def _on_hue(self, event) -> None:
        width = int(self.hue.cget("width"))
        self.h = min(max(event.x / (width - 1), 0.0), 1.0)
        self._render(update_hex=True)

    def _on_hex_typed(self, _event=None) -> None:
        color = t.normalize_hex(self.hex.get())
        if not color:
            return
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s > 0 and v > 0:  # grays and black have no hue: keep the bar where it is
            self.h = h
        self.s, self.v = s, v
        self._render(update_hex=False)

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.color)
        self.copy_btn.configure(text="Copied")
        self.after(1200, lambda: self.copy_btn.winfo_exists() and self.copy_btn.configure(text="Copy"))

    def _use(self) -> None:
        color = self.color
        self._close()
        self._on_pick(color)

    def _close(self) -> None:
        master = self.master
        self.destroy()
        try:  # give the modal grab back to the dialog that opened us
            master.grab_set()
            master.focus_force()
        except Exception:
            pass
