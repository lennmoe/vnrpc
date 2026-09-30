from __future__ import annotations

import re
import tkinter as tk

import customtkinter as ctk

from . import theme as t
from .color_picker import ColorPicker

_OVERRIDE_LINE = re.compile(r"^\s*([A-Za-z_]+)\s*[:=]?\s*(#?[0-9A-Fa-f]{3,6})\s*$")


class ThemeTab(ctk.CTkFrame):
    """Settings → Theme: pick a theme, and build the Custom one from a few hex colors
    (with a live preview and optional per-token overrides)."""

    def __init__(self, parent, cfg) -> None:
        super().__init__(parent, fg_color="transparent")
        custom = dict(cfg.get("custom_theme") or {})
        self._preview_job = None
        body = t.scrollable(self)
        body.pack(fill="both", expand=True)

        _section(body, "Theme")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 4))
        self._names = {label: name for name, label in t.theme_choices()}
        self.theme = t.option_menu(row, list(self._names), lambda _v: self._render_preview(), width=220)
        self.theme.set(next(label for label, name in self._names.items() if name == t.current_theme))
        self.theme.pack(side="left")
        t.muted(row, "Applied when you click Save.", size=11).pack(side="left", padx=12)

        _section(body, "Preview")
        self.preview_host = ctk.CTkFrame(body, fg_color="transparent")
        self.preview_host.pack(fill="x", padx=16)

        _section(body, "Custom theme")
        t.muted(body, "Used when Custom is selected. Pick four colors — hover, border and secondary "
                      "text colors are worked out from them.", size=11, wraplength=480).pack(fill="x", padx=16)

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(row, text="Base", font=t.font(13), text_color=t.TEXT, width=110, anchor="w").pack(side="left")
        self.mode = t.segmented(row, ["Dark", "Light"], command=lambda _v: self._custom_edited())
        self.mode.set("Light" if custom.get("mode") == "light" else "Dark")
        self.mode.pack(side="left")
        self.start_from = t.option_menu(
            row, [p["label"] for n, p in t.THEMES.items() if n != "custom"], self._start_from, width=150,
        )
        self.start_from.set("Start from…")
        self.start_from.pack(side="right")

        self.entries: dict[str, ctk.CTkEntry] = {}
        self.swatches: dict[str, ctk.CTkButton] = {}
        for key, label in t.CUSTOM_KEYS.items():
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=label, font=t.font(13), text_color=t.TEXT, width=110, anchor="w").pack(side="left")
            swatch = ctk.CTkButton(row, text="", width=34, height=30, corner_radius=8, border_width=1,
                                   border_color=t.BORDER, command=lambda k=key: self._pick(k))
            swatch.pack(side="left", padx=(0, 8))
            ent = t.entry(row, width=110, height=30)
            ent.insert(0, t.normalize_hex(custom.get(key)) or t.THEMES["dark"][key])
            ent.bind("<KeyRelease>", lambda _e: self._custom_edited())
            ent.pack(side="left")
            self.entries[key], self.swatches[key] = ent, swatch

        _section(body, "Advanced")
        t.muted(body, "Override any single color, one per line, e.g. GREEN #1A7F45. Available: "
                      + ", ".join(t.TOKENS), size=11, wraplength=480).pack(fill="x", padx=16, pady=(0, 6))
        self.overrides = ctk.CTkTextbox(
            body, height=90, font=t.mono(12), fg_color=t.SURFACE_ALT, border_color=t.BORDER, border_width=1,
            corner_radius=8, text_color=t.TEXT, wrap="none",
        )
        self.overrides.pack(fill="x", padx=16, pady=(0, 12))
        self.overrides.insert("1.0", "\n".join(f"{k} {v}" for k, v in (custom.get("overrides") or {}).items()))
        self.overrides.bind("<KeyRelease>", lambda _e: self._custom_edited())

        self._render_preview()

    def theme_name(self) -> str:
        return self._names.get(self.theme.get(), t.current_theme)

    def custom_value(self, *, strict: bool = True) -> dict:
        """The custom theme as stored in the config. ``strict``: raise ValueError on a
        bad hex code or override line; otherwise skip them (for the live preview)."""
        value: dict = {"mode": self.mode.get().lower()}
        for key, ent in self.entries.items():
            color = t.normalize_hex(ent.get())
            if color is None and strict:
                raise ValueError(f"{t.CUSTOM_KEYS[key]}: “{ent.get().strip()}” isn't a hex color like #FFDCE8.")
            if color:
                value[key] = color
        overrides: dict[str, str] = {}
        for n, line in enumerate(self.overrides.get("1.0", tk.END).splitlines(), start=1):
            if not line.strip():
                continue
            m = _OVERRIDE_LINE.match(line)
            token = m.group(1).upper() if m else ""
            color = t.normalize_hex(m.group(2)) if m else None
            if token in t.TOKENS and color:
                overrides[token] = color
            elif strict:
                raise ValueError(f"Advanced, line {n}: expected a color name and a hex code, "
                                 "e.g. GREEN #1A7F45.")
        value["overrides"] = overrides
        return value

    def _pick(self, key: str) -> None:
        def picked(color: str) -> None:
            self._set_entry(key, color)
            self._custom_edited(now=True)

        ColorPicker(self.winfo_toplevel(), self.entries[key].get(), picked,
                    title=f"{t.CUSTOM_KEYS[key]} color")

    def _start_from(self, label: str) -> None:
        name = next(n for n, p in t.THEMES.items() if p["label"] == label)
        palette = t.THEMES[name]
        self.mode.set(palette["mode"].capitalize())
        for key in self.entries:
            self._set_entry(key, palette[key])
        self.overrides.delete("1.0", tk.END)
        self.start_from.set("Start from…")
        self._custom_edited(now=True)

    def _set_entry(self, key: str, color: str) -> None:
        ent = self.entries[key]
        ent.delete(0, tk.END)
        ent.insert(0, color)

    def _custom_edited(self, *, now: bool = False) -> None:
        """Editing the custom colors means designing the Custom theme: select it, so the
        preview (and Save) use it."""
        custom_label = next(label for label, name in self._names.items() if name == "custom")
        self.theme.set(custom_label)
        if now:
            self._render_preview()
        else:
            self._schedule_preview()

    def _selected_palette(self) -> dict[str, str]:
        name = self.theme_name()
        if name == "custom":
            return t.build_custom_palette(self.custom_value(strict=False))
        return t.THEMES[t.windows_mode() if name == t.SYSTEM else name]

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(150, self._render_preview)

    def _render_preview(self) -> None:
        """A miniature of the main window in the selected theme (for Custom: in the
        colors being edited)."""
        self._preview_job = None
        custom = t.build_custom_palette(self.custom_value(strict=False))
        for key, swatch in self.swatches.items():
            swatch.configure(fg_color=custom[key], hover_color=custom[key])
        p = self._selected_palette()
        for w in self.preview_host.winfo_children():
            w.destroy()

        outer = ctk.CTkFrame(self.preview_host, fg_color=p["BG"], corner_radius=10)
        outer.pack(fill="x")
        card = ctk.CTkFrame(outer, fg_color=p["SURFACE"], border_width=1, border_color=p["BORDER"],
                            corner_radius=10)
        card.pack(fill="x", padx=14, pady=14)
        ctk.CTkLabel(card, text="NOW READING", font=t.font(11, "bold"), text_color=p["ACCENT"],
                     anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(card, text="Sayonara o Oshiete", font=t.font(18, "bold"), text_color=p["TEXT"],
                     anchor="w").pack(fill="x", padx=14)
        ctk.CTkLabel(card, text="SiglusEngine  ·  3h 40m read", font=t.font(12), text_color=p["MUTED"],
                     anchor="w").pack(fill="x", padx=14)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(row, text="  Day 10  ", fg_color=p["ACCENT"], text_color=p["ON_ACCENT"], corner_radius=8,
                     font=t.font(12, "bold"), height=26).pack(side="left")
        ctk.CTkLabel(row, text="  Finished  ", fg_color=p["SURFACE_ALT"], text_color=p["GREEN"], corner_radius=8,
                     font=t.font(12, "bold"), height=26).pack(side="left", padx=6)
        seg = ctk.CTkSegmentedButton(
            row, values=["Auto", "Manual"], fg_color=p["SURFACE_ALT"], unselected_color=p["SURFACE_ALT"],
            unselected_hover_color=p["SURFACE_HOVER"], selected_color=p["SELECTED"],
            selected_hover_color=p["SELECTED_HOVER"], text_color=p["TEXT"], corner_radius=8,
            font=t.font(12, "bold"), height=28,
        )
        seg.set("Manual")
        seg.pack(side="right")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkButton(row, text="▶  Play", width=90, height=32, corner_radius=8, fg_color=p["ACCENT"],
                      hover_color=p["ACCENT_HOVER"], text_color=p["ON_ACCENT"],
                      font=t.font(13, "bold")).pack(side="left")
        ctk.CTkButton(row, text="Library", width=90, height=32, corner_radius=8, fg_color=p["SURFACE_ALT"],
                      hover_color=p["SURFACE_HOVER"], text_color=p["TEXT"], border_width=1,
                      border_color=p["BORDER"], font=t.font(13)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Remove", width=90, height=32, corner_radius=8, fg_color="transparent",
                      hover_color=p["DANGER_HOVER"], text_color=p["RED"], border_width=1,
                      border_color=p["DANGER_BORDER"], font=t.font(13)).pack(side="left")

        bar = ctk.CTkProgressBar(card, height=4, corner_radius=2, progress_color=p["ACCENT"],
                                 fg_color=p["SURFACE_ALT"])
        bar.set(0.62)
        bar.pack(fill="x", padx=14, pady=(12, 14))


def _section(parent, title: str) -> None:
    t.overline(parent, title, color=t.ACCENT).pack(fill="x", padx=16, pady=(16, 6))
