from __future__ import annotations

from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from . import theme as t
from .color_picker import ColorPicker

TILE_W, PREVIEW_H, TILE_H = 180, 100, 128
_SCALE = 2  # drawn at twice the size, so it stays sharp with Windows display scaling
_GAP = 14

ApplyTheme = Callable[[str, "dict | None"], None]


class ThemeTab(ctk.CTkFrame):
    """Settings → Theme: every theme as a small preview of its colors; clicking one
    uses it right away. The Custom theme is made from four colors."""

    def __init__(self, parent, cfg, on_apply: ApplyTheme) -> None:
        super().__init__(parent, fg_color="transparent")
        self._on_apply = on_apply
        custom = dict(cfg.get("custom_theme") or {})
        self._custom: dict = {"mode": "light" if custom.get("mode") == "light" else "dark"}
        for key in t.CUSTOM_KEYS:
            self._custom[key] = t.normalize_hex(custom.get(key)) or t.THEMES["dark"][key]
        self._tiles: dict[str, ctk.CTkLabel] = {}
        self._hover = ""

        body = t.scrollable(self)
        body.pack(fill="both", expand=True)
        t.muted(body, "Click a theme to use it.", size=12).pack(fill="x", padx=16, pady=(14, 0))

        dark = [n for n, p in t.THEMES.items() if n != "custom" and p["mode"] == "dark"]
        light = [n for n, p in t.THEMES.items() if n != "custom" and p["mode"] == "light"]
        for title, names in (("Automatic", [t.SYSTEM]), ("Dark", dark), ("Light", light)):
            _section(body, title)
            grid = _TileGrid(body)
            grid.pack(fill="x", padx=16)
            for name in names:
                grid.add(self._make_tile(grid, name))

        _section(body, "Your own")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        self._make_tile(row, "custom").pack(side="left", anchor="n")
        self._build_editor(row)

    # -- tiles -----------------------------------------------------------------
    def _make_tile(self, parent, name: str) -> ctk.CTkLabel:
        tile = ctk.CTkLabel(parent, text="", cursor="hand2")
        tile.bind("<Button-1>", lambda _e: self._choose(name))
        tile.bind("<Enter>", lambda _e: self._set_hover(name))
        tile.bind("<Leave>", lambda _e: self._set_hover(""))
        self._tiles[name] = tile
        self._render_tile(name)
        return tile

    def _render_tile(self, name: str) -> None:
        if name == t.SYSTEM:
            palettes, label = (t.THEMES["dark"], t.THEMES["light"]), "Match Windows"
        elif name == "custom":
            palettes, label = (t.build_custom_palette(self._custom),), "Custom"
        else:
            palettes, label = (t.THEMES[name],), t.THEMES[name]["label"]
        selected = name == t.current_theme
        ring = t.resolve(t.ACCENT) if selected else t.resolve(t.SUBTLE) if name == self._hover else None
        img = tile_image(palettes, label, ring=ring, bold=selected,
                         label_color=t.resolve(t.ACCENT if selected else t.TEXT))
        self._tiles[name].configure(image=ctk.CTkImage(light_image=img, dark_image=img, size=(TILE_W, TILE_H)))

    def _set_hover(self, name: str) -> None:
        old, self._hover = self._hover, name
        for n in {old, name} - {""}:
            if n in self._tiles:
                self._render_tile(n)

    def _choose(self, name: str) -> None:
        if name == "custom":
            self._on_apply("custom", dict(self._custom))
        elif name != t.current_theme:
            self._on_apply(name, None)

    # -- custom theme ----------------------------------------------------------
    def _build_editor(self, parent) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True, padx=(18, 0))
        t.muted(box, "Pick four colors; the rest is worked out from them.", size=11).pack(anchor="w")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(anchor="w", pady=(8, 4))
        self.mode = t.segmented(row, ["Dark", "Light"], command=lambda v: self._edit(mode=v.lower()))
        self.mode.set(self._custom["mode"].capitalize())
        self.mode.pack(side="left")

        self._swatches: dict[str, tuple[ctk.CTkButton, ctk.CTkLabel]] = {}
        colors = ctk.CTkFrame(box, fg_color="transparent")
        colors.pack(anchor="w", pady=(4, 0))
        for i, (key, label) in enumerate(t.CUSTOM_KEYS.items()):
            cell = ctk.CTkFrame(colors, fg_color="transparent")
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 18), pady=3)
            swatch = ctk.CTkButton(cell, text="", width=34, height=30, corner_radius=8, border_width=1,
                                   border_color=t.BORDER, command=lambda k=key: self._pick(k))
            swatch.pack(side="left")
            name = ctk.CTkLabel(cell, text=label, font=t.font(13), text_color=t.TEXT, width=90, anchor="w")
            name.pack(side="left", padx=(8, 0))
            self._swatches[key] = (swatch, name)

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(anchor="w", pady=(10, 0))
        t.primary_button(btns, "Use my colors", lambda: self._choose("custom"), width=130).pack(side="left")
        t.secondary_button(btns, "Start from the current theme", self._copy_current, width=210).pack(
            side="left", padx=(8, 0))
        self._show_swatches()

    def _show_swatches(self) -> None:
        for key, (swatch, _name) in self._swatches.items():
            swatch.configure(fg_color=self._custom[key], hover_color=self._custom[key])

    def _pick(self, key: str) -> None:
        ColorPicker(self.winfo_toplevel(), self._custom[key], lambda color, k=key: self._edit(**{k: color}),
                    title=f"{t.CUSTOM_KEYS[key]} color")

    def _copy_current(self) -> None:
        palette = t.THEMES[t.resolved_theme]
        self.mode.set(palette["mode"].capitalize())
        self._edit(mode=palette["mode"], **{k: palette[k] for k in t.CUSTOM_KEYS})

    def _edit(self, **changes) -> None:
        self._custom.update(changes)
        self._show_swatches()
        self._render_tile("custom")


class _TileGrid(ctk.CTkFrame):
    """Lays its tiles out in as many columns as fit, again whenever it's resized."""

    def __init__(self, parent) -> None:
        super().__init__(parent, fg_color="transparent")
        self._items: list = []
        self._cols = 0
        self.bind("<Configure>", lambda e: self._layout(e.width))

    def add(self, widget) -> None:
        self._items.append(widget)
        self._layout(self.winfo_width())

    def _layout(self, width: int) -> None:
        scale = max(1.0, ctk.ScalingTracker.get_widget_scaling(self))
        cols = max(1, int((width / scale + _GAP) // (TILE_W + _GAP))) if width > 1 else 4
        if cols == self._cols and all(w.winfo_manager() for w in self._items):
            return
        self._cols = cols
        for i, widget in enumerate(self._items):
            widget.grid(row=i // cols, column=i % cols, padx=(0, _GAP), pady=(0, _GAP), sticky="nw")


def tile_image(palettes: tuple[dict, ...], label: str, *, ring: str | None, bold: bool,
               label_color: str) -> Image.Image:
    """A theme's tile: a miniature window in its colors (two side by side for "Match
    Windows"), with the theme's name under it. Transparent around the corners."""
    s = _SCALE
    w, ph, h = TILE_W * s, PREVIEW_H * s, TILE_H * s
    preview = _miniature(palettes[0], w, ph)
    if len(palettes) > 1:
        # The other palette's half starts after the text lines, so they aren't cut in two.
        split = int(w * 0.58)
        preview.paste(_miniature(palettes[1], w, ph).crop((split, 0, w, ph)), (split, 0))
    mask = Image.new("L", (w, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, ph - 1), radius=10 * s, fill=255)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(preview, (0, 0), mask)
    draw = ImageDraw.Draw(img)
    if ring:
        draw.rounded_rectangle((1, 1, w - 2, ph - 2), radius=10 * s, outline=ring, width=3 * s)
    draw.text((2 * s, ph + 7 * s), label, fill=label_color, font=_font(13 * s, bold))
    return img


def _miniature(p: dict, w: int, h: int) -> Image.Image:
    """A tiny "now reading" card in palette ``p``."""
    s = _SCALE
    img = Image.new("RGBA", (w, h), p["BG"])
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 14 * s, 14 * s, w - 14 * s, h - 14 * s
    d.rounded_rectangle((x0, y0, x1, y1), radius=8 * s, fill=p["SURFACE"], outline=p["BORDER"], width=s)
    x = x0 + 12 * s
    d.rounded_rectangle((x, y0 + 12 * s, x + 74 * s, y0 + 20 * s), radius=4 * s, fill=p["TEXT"])
    d.rounded_rectangle((x, y0 + 26 * s, x + 50 * s, y0 + 32 * s), radius=3 * s, fill=p["MUTED"])
    d.rounded_rectangle((x, y0 + 41 * s, x + 46 * s, y0 + 56 * s), radius=7 * s, fill=p["ACCENT"])
    d.rounded_rectangle((x + 10 * s, y0 + 47 * s, x + 36 * s, y0 + 50 * s), radius=2 * s, fill=p["ON_ACCENT"])
    d.rounded_rectangle((x + 52 * s, y0 + 41 * s, x + 90 * s, y0 + 56 * s), radius=7 * s,
                        fill=p["SURFACE_ALT"], outline=p["BORDER"], width=s)
    bar_y = y1 - 9 * s
    d.rounded_rectangle((x, bar_y, x1 - 12 * s, bar_y + 3 * s), radius=s, fill=p["SURFACE_ALT"])
    d.rounded_rectangle((x, bar_y, x + int((x1 - 12 * s - x) * 0.6), bar_y + 3 * s), radius=s, fill=p["ACCENT"])
    return img


_fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool):
    key = (size, bold)
    if key not in _fonts:
        for name in (("seguisb.ttf", "segoeuib.ttf") if bold else ("segoeui.ttf",)) + ("arial.ttf",):
            try:
                _fonts[key] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _fonts[key] = ImageFont.load_default(size=size)
    return _fonts[key]


def _section(parent, title: str) -> None:
    t.overline(parent, title, color=t.ACCENT).pack(fill="x", padx=16, pady=(16, 8))
