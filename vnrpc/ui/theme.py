from __future__ import annotations

import math
import sys

import customtkinter as ctk

from ..paths import APP_ICON_ICO

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "label": "Dark", "mode": "dark",
        "BG": "#111214", "SURFACE": "#1B1C20", "SURFACE_ALT": "#24262B", "SURFACE_HOVER": "#2E3036",
        "BORDER": "#2B2D33", "TEXT": "#F2F3F5", "MUTED": "#A3A7B0", "SUBTLE": "#6F737C",
        "ACCENT": "#5865F2", "ACCENT_HOVER": "#4752C4", "ACCENT_SOFT": "#2A2D52", "ON_ACCENT": "#FFFFFF",
        "SELECTED": "#5865F2", "SELECTED_HOVER": "#4752C4",
        "GREEN": "#23A55A", "RED": "#F23F43", "DANGER_HOVER": "#3A1F22", "DANGER_BORDER": "#5A2A2E",
        "YELLOW": "#F0B232", "YELLOW_HOVER": "#D69E2B", "YELLOW_SOFT": "#3A3120", "ON_YELLOW": "#1E1F22",
        "SWITCH_OFF": "#3A3D44", "SWITCH_KNOB": "#F2F3F5",
        "PLACEHOLDER_TOP": "#2B2D42", "PLACEHOLDER_BOTTOM": "#1C1D24", "PLACEHOLDER_FG": "#6E748C",
    },
    "light": {
        "label": "Light", "mode": "light",
        "BG": "#F2F3F5", "SURFACE": "#FFFFFF", "SURFACE_ALT": "#E8E9ED", "SURFACE_HOVER": "#DCDEE3",
        "BORDER": "#D6D8DD", "TEXT": "#1E1F22", "MUTED": "#5C5F66", "SUBTLE": "#80848E",
        "ACCENT": "#5865F2", "ACCENT_HOVER": "#4752C4", "ACCENT_SOFT": "#E3E5FD", "ON_ACCENT": "#FFFFFF",
        "SELECTED": "#B7BDF9", "SELECTED_HOVER": "#A5ACF5",
        "GREEN": "#1A7F45", "RED": "#D92D35", "DANGER_HOVER": "#FBE1E2", "DANGER_BORDER": "#F3B8BA",
        "YELLOW": "#9A6A00", "YELLOW_HOVER": "#7F5800", "YELLOW_SOFT": "#FCF1D6", "ON_YELLOW": "#FFFFFF",
        "SWITCH_OFF": "#C4C7CE", "SWITCH_KNOB": "#FFFFFF",
        "PLACEHOLDER_TOP": "#E3E5EC", "PLACEHOLDER_BOTTOM": "#D3D6DE", "PLACEHOLDER_FG": "#8A8FA0",
    },
    "sakura": {
        "label": "Sakura", "mode": "light",
        "BG": "#FFDCE8", "SURFACE": "#FBE3EB", "SURFACE_ALT": "#F6D3DF", "SURFACE_HOVER": "#EFC3D3",
        "BORDER": "#EFC3D3", "TEXT": "#3A2230", "MUTED": "#7B5566", "SUBTLE": "#A07A8B",
        "ACCENT": "#C73E72", "ACCENT_HOVER": "#A8305E", "ACCENT_SOFT": "#F5C2D5", "ON_ACCENT": "#FFFFFF",
        "SELECTED": "#EC94B5", "SELECTED_HOVER": "#E3809F",
        "GREEN": "#17703F", "RED": "#C8283E", "DANGER_HOVER": "#F9CFD6", "DANGER_BORDER": "#EBA5B3",
        "YELLOW": "#8A5E00", "YELLOW_HOVER": "#6F4B00", "YELLOW_SOFT": "#FBE7C8", "ON_YELLOW": "#FFFFFF",
        "SWITCH_OFF": "#E3B3C4", "SWITCH_KNOB": "#FFFFFF",
        "PLACEHOLDER_TOP": "#F6CFDC", "PLACEHOLDER_BOTTOM": "#EDBBCD", "PLACEHOLDER_FG": "#B0788E",
    },
}
DEFAULT_THEME = "dark"
TOKENS = tuple(k for k in THEMES["dark"] if k.isupper())

# The four colors a custom theme is made from; everything else is derived.
CUSTOM_KEYS = {"BG": "Background", "SURFACE": "Cards", "ACCENT": "Accent", "TEXT": "Text"}


def normalize_hex(value) -> str | None:
    """``"fdc"``, ``"#FFDDCC"``, ``"ffddcc"`` -> ``"#FFDDCC"``; anything else -> None."""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        return None
    return "#" + text.upper()


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def mix(a: str, b: str, amount: float) -> str:
    """``amount`` of the way from color ``a`` to color ``b``."""
    return "#" + "".join(f"{round(x + (y - x) * amount):02X}" for x, y in zip(_rgb(a), _rgb(b)))


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two colors (1 … 21)."""
    def lum(color: str) -> float:
        chans = [c / 255 for c in _rgb(color)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def build_custom_palette(custom: dict | None) -> dict[str, str]:
    """A full palette from a custom theme's four colors (``CUSTOM_KEYS``), its light or
    dark ``mode``, and optional per-token ``overrides``. Invalid colors fall back to
    the base theme's."""
    custom = custom or {}
    mode = "light" if custom.get("mode") == "light" else "dark"
    base = THEMES[mode]
    pick = {k: normalize_hex(custom.get(k)) or base[k] for k in CUSTOM_KEYS}
    bg, surface, accent, text = pick["BG"], pick["SURFACE"], pick["ACCENT"], pick["TEXT"]
    alt = mix(surface, text, 0.07)
    selected = accent
    for step in range(29):  # the selected segment keeps TEXT on it, so it must stay readable
        selected = mix(alt, accent, 1 - step * 0.035)
        if contrast(text, selected) >= 4.5:
            break
    on_accent = "#FFFFFF" if contrast("#FFFFFF", accent) >= contrast("#111111", accent) else "#111111"
    palette = dict(base)
    palette.update(
        label="Custom", mode=mode, BG=bg, SURFACE=surface, SURFACE_ALT=alt,
        SURFACE_HOVER=mix(surface, text, 0.13), BORDER=mix(surface, text, 0.12),
        TEXT=text, MUTED=mix(text, surface, 0.3), SUBTLE=mix(text, surface, 0.55),
        ACCENT=accent, ACCENT_HOVER=mix(accent, "#000000", 0.18), ACCENT_SOFT=mix(surface, accent, 0.22),
        ON_ACCENT=on_accent, SELECTED=selected, SELECTED_HOVER=mix(selected, text, 0.1),
        DANGER_HOVER=mix(surface, base["RED"], 0.15), DANGER_BORDER=mix(surface, base["RED"], 0.45),
        YELLOW_SOFT=mix(surface, base["YELLOW"], 0.2), SWITCH_OFF=mix(surface, text, 0.28),
        PLACEHOLDER_TOP=mix(surface, accent, 0.14), PLACEHOLDER_BOTTOM=mix(surface, text, 0.08),
        PLACEHOLDER_FG=mix(text, surface, 0.5),
    )
    for token, value in (custom.get("overrides") or {}).items():
        color = normalize_hex(value)
        if token in TOKENS and color:
            palette[token] = color
    return palette


def set_custom_theme(custom: dict | None) -> None:
    """(Re)build the "Custom" entry of :data:`THEMES` from the config's ``custom_theme``."""
    THEMES["custom"] = build_custom_palette(custom)


def _preset(label: str, mode: str, bg: str, surface: str, accent: str, text: str,
            **overrides: str) -> dict[str, str]:
    palette = build_custom_palette({"mode": mode, "BG": bg, "SURFACE": surface, "ACCENT": accent, "TEXT": text,
                                    "overrides": overrides})
    palette["label"] = label
    return palette


THEMES.update(
    butter=_preset("Butter", "light", "#FFF1C7", "#FFF8E1", "#E0661A", "#4A2A12"),
    lilac=_preset("Lilac", "light", "#CBCFF4", "#FFF9DC", "#5B5FC7", "#2F2C57"),
    sky=_preset("Sky", "light", "#69D0F1", "#EFEDD1", "#15729A", "#16323F"),
    mint=_preset("Neon Mint", "dark", "#101516", "#182122", "#54E6D4", "#E6F7F4"),
    amoled=_preset("AMOLED Black", "dark", "#000000", "#0E0F11", "#5865F2", "#F2F3F5"),
    dracula=_preset("Dracula", "dark", "#282A36", "#343746", "#BD93F9", "#F8F8F2"),
    nord=_preset("Nord", "dark", "#2E3440", "#3B4252", "#88C0D0", "#ECEFF4"),
    mocha=_preset("Catppuccin Mocha", "dark", "#1E1E2E", "#313244", "#CBA6F7", "#CDD6F4"),
    tokyo=_preset("Tokyo Night", "dark", "#1A1B26", "#24283B", "#7AA2F7", "#C0CAF5"),
    gruvbox=_preset("Gruvbox", "dark", "#282828", "#3C3836", "#FABD2F", "#EBDBB2"),
    rosepine=_preset("Rosé Pine", "dark", "#191724", "#1F1D2E", "#EBBCBA", "#E0DEF4"),
    latte=_preset("Catppuccin Latte", "light", "#DCE0E8", "#EFF1F5", "#8839EF", "#4C4F69", MUTED="#5C5F77"),
    solarized=_preset("Solarized Light", "light", "#EEE8D5", "#FDF6E3", "#268BD2", "#073642"),
)
set_custom_theme(None)  # last, so "Custom" ends the list

SYSTEM = "system"  # not a palette: Dark or Light, whichever Windows apps use


def windows_mode() -> str:
    """``"light"`` or ``"dark"``: the app mode set in Windows' color settings."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except (ImportError, OSError):
        return "dark"



BG = SURFACE = SURFACE_ALT = SURFACE_HOVER = BORDER = TEXT = MUTED = SUBTLE = ""
ACCENT = ACCENT_HOVER = ACCENT_SOFT = ON_ACCENT = SELECTED = SELECTED_HOVER = GREEN = RED = DANGER_HOVER = DANGER_BORDER = ""
YELLOW = YELLOW_HOVER = YELLOW_SOFT = ON_YELLOW = SWITCH_OFF = SWITCH_KNOB = ""
PLACEHOLDER_TOP = PLACEHOLDER_BOTTOM = PLACEHOLDER_FG = ""
STATUS_COLORS: dict[str, str] = {}
current_theme = ""   # what the user picked (may be "system")
resolved_theme = ""  # the palette actually in use

RADIUS = 12


def apply_theme(name: str) -> None:
    """Point every color token at theme ``name`` (unknown names fall back to Dark;
    ``"system"`` follows Windows' light/dark setting)."""
    global current_theme, resolved_theme
    if name == SYSTEM:
        current_theme, resolved_theme = SYSTEM, windows_mode()
    else:
        current_theme = resolved_theme = name if name in THEMES else DEFAULT_THEME
    palette = THEMES[resolved_theme]
    globals().update({k: v for k, v in palette.items() if k.isupper()})
    STATUS_COLORS.update(playing=ACCENT, finished=GREEN, stalled=YELLOW, dropped=MUTED)
    ctk.set_appearance_mode(palette["mode"])


def stop_restyling(widgets) -> None:
    """Take ``widgets`` and everything in them out of CustomTkinter's light/dark
    tracking: they're about to be destroyed, and switching between a light and a
    dark theme would otherwise repaint every one of them first."""
    ids: set[int] = set()
    stack = list(widgets)
    while stack:
        widget = stack.pop()
        ids.add(id(widget))
        stack.extend(widget.winfo_children())
    callbacks = ctk.AppearanceModeTracker.callback_list
    callbacks[:] = [cb for cb in callbacks if id(getattr(cb, "__self__", None)) not in ids]


def resolve(color) -> str:
    """A ``(light, dark)`` pair as the single color plain tk widgets (Canvas) need."""
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


apply_theme(DEFAULT_THEME)


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def mono(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(family="Consolas", size=size)


def primary_button(parent, text: str, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 34)
    return ctk.CTkButton(
        parent, text=text, command=command, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        text_color=ON_ACCENT, corner_radius=8, font=font(13, "bold"), **kw,
    )


def secondary_button(parent, text: str, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 34)
    return ctk.CTkButton(
        parent, text=text, command=command, fg_color=SURFACE_ALT, hover_color=SURFACE_HOVER,
        text_color=TEXT, border_width=1, border_color=BORDER, corner_radius=8, font=font(13), **kw,
    )


def danger_button(parent, text: str, command=None, **kw) -> ctk.CTkButton:
    kw.setdefault("height", 34)
    return ctk.CTkButton(
        parent, text=text, command=command, fg_color="transparent", hover_color=DANGER_HOVER,
        text_color=RED, border_width=1, border_color=DANGER_BORDER, corner_radius=8,
        font=font(13), **kw,
    )


def link_button(parent, text: str, command=None, **kw) -> ctk.CTkButton:
    """A borderless button that reads as a link, e.g. "← Library" at the top of a page."""
    kw.setdefault("height", 28)
    return ctk.CTkButton(
        parent, text=text, command=command, fg_color="transparent", hover_color=SURFACE_HOVER,
        text_color=MUTED, corner_radius=8, font=font(13), width=0, **kw,
    )


def page_title(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(20, "bold"), text_color=TEXT, anchor="w")


def card(parent, **kw) -> ctk.CTkFrame:
    kw.setdefault("corner_radius", RADIUS)
    return ctk.CTkFrame(parent, fg_color=SURFACE, border_width=1, border_color=BORDER, **kw)


def panel(parent, **kw) -> ctk.CTkFrame:
    kw.setdefault("corner_radius", 10)
    return ctk.CTkFrame(parent, fg_color=SURFACE_ALT, **kw)


def overline(parent, text: str, color=None) -> ctk.CTkLabel:
    """Small all-caps section label."""
    return ctk.CTkLabel(parent, text=text.upper(), font=font(11, "bold"), text_color=color or SUBTLE,
                        anchor="w")


def muted(parent, text: str = "", size: int = 12, **kw) -> ctk.CTkLabel:
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return ctk.CTkLabel(parent, text=text, font=font(size), text_color=MUTED, **kw)


def chip(parent, text: str = "", *, fg_color=None, text_color=None) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text, fg_color=fg_color or ACCENT_SOFT, text_color=text_color or TEXT, corner_radius=8,
        font=font(12, "bold"), height=26,
    )


def entry(parent, **kw) -> ctk.CTkEntry:
    kw.setdefault("height", 34)
    return ctk.CTkEntry(
        parent, fg_color=SURFACE_ALT, border_color=BORDER, border_width=1, corner_radius=8,
        text_color=TEXT, **kw,
    )


def segmented(parent, values: list[str], command=None, **kw) -> ctk.CTkSegmentedButton:
    return ctk.CTkSegmentedButton(
        parent, values=values, command=command, fg_color=SURFACE_ALT, unselected_color=SURFACE_ALT,
        unselected_hover_color=SURFACE_HOVER, selected_color=SELECTED, selected_hover_color=SELECTED_HOVER,
        text_color=TEXT, corner_radius=8, font=font(12, "bold"), height=30, **kw,
    )


def option_menu(parent, values: list[str], command=None, **kw) -> ctk.CTkOptionMenu:
    kw.setdefault("height", 30)
    return ctk.CTkOptionMenu(
        parent, values=values, command=command, corner_radius=8, fg_color=SURFACE_ALT,
        button_color=SURFACE_HOVER, button_hover_color=BORDER, text_color=TEXT, dropdown_fg_color=SURFACE,
        dropdown_hover_color=SURFACE_HOVER, dropdown_text_color=TEXT, font=font(12), **kw,
    )


def switch(parent, text: str, value: bool, hint: str = "") -> ctk.CTkSwitch:
    """A labelled toggle row, optionally with a muted one-line explanation under it."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=(6, 0 if hint else 6))
    sw = ctk.CTkSwitch(
        row, text=text, font=font(13), text_color=TEXT, progress_color=ACCENT,
        button_color=SWITCH_KNOB, button_hover_color=SWITCH_KNOB, fg_color=SWITCH_OFF,
    )
    sw.pack(anchor="w")
    if hint:
        muted(row, hint, size=11, wraplength=440).pack(anchor="w", padx=(50, 0), pady=(0, 4))
    if value:
        sw.select()
    else:
        sw.deselect()
    return sw


class SmoothScrollableFrame(ctk.CTkScrollableFrame):
    """On Windows CTkScrollableFrame jumps 20px per wheel notch; this glides ~90px
    over a few frames instead (and keeps up when the wheel is spun quickly)."""

    STEP = 90  # pixels per wheel notch
    EASE = 0.35  # share of the remaining distance covered each frame
    FRAME_MS = 12

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self._scroll_target = 0.0
        self._scroll_job = None
        # CTk recomputes the scroll region and redraws its scrollbar (a costly canvas
        # drawing) on every resize of the content: dozens of times while a page is
        # being built. Do each once, when Tk is idle.
        self._region_job = None
        self._bar_job = None
        self._bar_value: tuple[str, str] | None = None
        self._bar_drawn: tuple[str, str] | None = None
        if self._orientation == "vertical":
            self.bind("<Configure>", self._queue_region)
            self._parent_canvas.configure(yscrollcommand=self._queue_bar)

    def _queue_region(self, _event=None) -> None:
        if self._region_job is None:
            self._region_job = self.after_idle(self._update_region)

    def _update_region(self) -> None:
        self._region_job = None
        self._parent_canvas.configure(scrollregion=self._parent_canvas.bbox("all"))

    def _queue_bar(self, first: str, last: str) -> None:
        self._bar_value = (first, last)
        if self._bar_job is None:
            self._bar_job = self.after_idle(self._update_bar)

    def _update_bar(self) -> None:
        self._bar_job = None
        if self._bar_value != self._bar_drawn:
            self._bar_drawn = self._bar_value
            self._scrollbar.set(*self._bar_value)

    def destroy(self) -> None:
        for job in (self._region_job, self._bar_job, self._scroll_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        super().destroy()

    def _mouse_wheel_all(self, event):
        if (not sys.platform.startswith("win") or self._shift_pressed
                or not self._check_if_valid_scroll(event.widget)):
            return super()._mouse_wheel_all(event)
        canvas = self._parent_canvas
        region = canvas.bbox("all")
        if not region:
            return
        bottom = max(0.0, region[3] - canvas.winfo_height())
        start = self._scroll_target if self._scroll_job else canvas.canvasy(0)
        self._scroll_target = min(max(0.0, start - event.delta / 120 * self.STEP), bottom)
        if self._scroll_job is None:
            self._scroll_step()

    def _scroll_step(self) -> None:
        self._scroll_job = None
        try:
            canvas = self._parent_canvas
            before = canvas.canvasy(0)
        except Exception:  # destroyed mid-animation
            return
        remaining = self._scroll_target - before
        if abs(remaining) < 1:
            return
        move = math.copysign(max(1.0, abs(remaining) * self.EASE), remaining)
        canvas.yview_scroll(int(round(move)), "units")  # 1 unit = 1px on Windows
        if canvas.canvasy(0) != before:  # stop at either end
            self._scroll_job = self.after(self.FRAME_MS, self._scroll_step)


def scrollable(parent, **kw) -> ctk.CTkScrollableFrame:
    return SmoothScrollableFrame(
        parent, fg_color="transparent", scrollbar_button_color=SURFACE_HOVER,
        scrollbar_button_hover_color=SUBTLE, **kw,
    )


def ellipsize(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def setup_window(win, *, title: str, geometry: str | None = None, minsize: tuple[int, int] | None = None,
                 resizable: bool = True, modal_for=None) -> None:
    """Common Toplevel setup: title, size, app icon, background, and (optionally)
    modal to ``modal_for``."""
    win.title(title)
    if geometry:
        win.geometry(geometry)
    if minsize:
        win.minsize(*minsize)
    win.resizable(resizable, resizable)
    win.configure(fg_color=BG)
    set_icon(win)
    if modal_for is not None:
        win.transient(modal_for.winfo_toplevel())
        win.after(80, lambda: _safe_grab(win))


def set_icon(win) -> None:
    if APP_ICON_ICO.exists():
        try:
            win.iconbitmap(str(APP_ICON_ICO))
        except Exception:
            pass


def _safe_grab(win) -> None:
    try:
        if win.winfo_exists():
            win.grab_set()
            win.focus_force()
    except Exception:
        pass
