from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .. import stats
from ..config import STATUSES
from ..core import VNRPCEngine, format_playtime
from ..covers import cached_cover_for_entry
from ..engines import is_blacklisted
from . import theme as t
from .game_page import display_name, launch_game, locate_game, remove_game
from .images import load_photo

THUMB = (60, 84)
# Cards built before the page is first drawn (about a screenful); the rest follow
# in small batches right after, so a big Library still shows up at once.
_FIRST_CARDS = 6
_CARD_BATCH = 4
_SORTS = ("Most read", "Recent", "A–Z")
_ALL = "All statuses"


class LibraryPage(ctk.CTkFrame):
    """Every VN played, with time read; a card opens the game's page."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.engine: VNRPCEngine = app.engine

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 10))
        t.page_title(head, "Library").pack(side="left")
        self.search = t.entry(head, placeholder_text="Filter…", width=220)
        self.search.pack(side="right")
        self.search.bind("<KeyRelease>", lambda _e: self._reload())

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=20, pady=(0, 8))
        self.sort = t.segmented(tools, list(_SORTS), command=lambda _v: self._reload())
        self.sort.set(_SORTS[0])
        self.sort.pack(side="left")
        self.status_filter = ctk.CTkOptionMenu(
            tools, values=[_ALL] + [s.capitalize() for s in STATUSES], command=lambda _v: self._reload(),
            width=140, height=30, corner_radius=8, fg_color=t.SURFACE_ALT, button_color=t.SURFACE_HOVER,
            button_hover_color=t.BORDER, text_color=t.TEXT, dropdown_fg_color=t.SURFACE,
            dropdown_hover_color=t.SURFACE_HOVER, dropdown_text_color=t.TEXT, font=t.font(12),
        )
        self.status_filter.set(_ALL)
        self.status_filter.pack(side="right")
        t.secondary_button(tools, "Random from wishlist", app.show_wishlist, width=160,
                           height=30).pack(side="right", padx=(0, 8))

        self.summary = t.muted(self, "")
        self.summary.pack(fill="x", padx=20, pady=(0, 8))

        self.list_box = t.scrollable(self)
        self.list_box.pack(fill="both", expand=True, padx=12, pady=(0, 14))
        # What's on screen: the keys in order, and per key what its card was built
        # from and the widgets that change while a VN is read (time, progress).
        self._shown: list[str] | None = None
        self._cards: dict[str, tuple[tuple, tk.Label, _Bar]] = {}
        self._build_job = None  # the next batch of cards still to build

    def on_show(self) -> None:
        self._reload()

    def _reload(self) -> None:
        if not self.winfo_exists():
            return
        blacklist = self.engine.blacklist
        games = {
            key: entry for key, entry in self.engine.config.all_games().items()
            if not is_blacklisted(entry.get("path") or key.split("@", 1)[0], blacklist)
        }
        total = sum(int(e.get("playtime_seconds", 0)) for e in games.values())
        week = sum(stats.this_week_seconds(e.get("daily")) for e in games.values())
        count = len(games)
        self.summary.configure(
            text=f"{count} game{'s' if count != 1 else ''}  ·  {format_playtime(total)} read in total"
                 f"  ·  {format_playtime(week)} this week"
            if count else ""
        )

        needle = self.search.get().strip().lower()
        wanted_status = self.status_filter.get().lower()
        entries = [
            (key, entry) for key, entry in games.items()
            if (not needle or needle in display_name(key, entry).lower() or needle in key)
            and (wanted_status == _ALL.lower() or entry.get("status") == wanted_status)
        ]
        sort = self.sort.get()
        if sort == "Recent":
            entries.sort(key=lambda kv: int(kv[1].get("last_played", 0)), reverse=True)
        elif sort == "A–Z":
            entries.sort(key=lambda kv: display_name(*kv).lower())
        else:
            entries.sort(key=lambda kv: int(kv[1].get("playtime_seconds", 0)), reverse=True)

        top = max(1, max((int(e.get("playtime_seconds", 0)) for _, e in entries), default=0))
        if self._build_job is None and self._refresh_in_place(entries, top):
            return
        if self._build_job is not None:
            self.after_cancel(self._build_job)
            self._build_job = None
        for w in self.list_box.winfo_children():
            w.destroy()
        self._cards.clear()
        self._shown = [key for key, _ in entries]
        if not entries:
            msg = ("No match." if needle or wanted_status != _ALL.lower() else
                   "Nothing here yet — start a visual novel with Visual Novel RPC running.")
            t.muted(self.list_box, msg, anchor="center", justify="center").pack(pady=40)
            return
        self._build_cards(entries, top, _FIRST_CARDS)

    def _build_cards(self, entries: list, top: int, count: int) -> None:
        for key, entry in entries[:count]:
            self._row(key, entry, top)
        rest = entries[count:]
        self._build_job = self.after(1, lambda: self._build_cards(rest, top, _CARD_BATCH)) if rest else None

    def _refresh_in_place(self, entries: list, top: int) -> bool:
        """When the same cards are listed in the same order, only update their time
        read and progress bar instead of building them all again (much faster)."""
        if self._shown != [key for key, _ in entries] or not entries:
            return False
        if any(self._cards[key][0] != _card_shape(key, entry) for key, entry in entries):
            return False
        for key, entry in entries:
            _shape, sub, bar = self._cards[key]
            text, value = _card_progress(entry, top)
            if sub.cget("text") != text:
                sub.configure(text=text)
            if abs(bar.get() - value) > 0.001:
                bar.set(value)
        return True

    def _row(self, key: str, entry: dict, top: int) -> None:
        # Only what needs rounded corners (the card, the status chip, the buttons) is
        # a CustomTkinter widget: the rest are plain tk ones, many times cheaper to
        # build, sized by hand for the display scaling.
        row = t.card(self.list_box, corner_radius=10)
        row.pack(fill="x", pady=5, padx=6)
        row.grid_columnconfigure(1, weight=1)
        s = ctk.ScalingTracker.get_widget_scaling(row)
        bg = t.resolve(t.SURFACE)
        px = lambda v: round(v * s)  # noqa: E731

        photo = load_photo(cached_cover_for_entry(entry), THUMB, radius=6, bg=bg, scale=s)
        thumb = tk.Label(row, image=photo, bg=bg, bd=0)
        thumb.grid(row=0, column=0, rowspan=3, padx=px(12), pady=px(12))

        name = display_name(key, entry)
        # (CTkLabels are 28px high with the text centered: the ipady keep the same spacing.)
        name_lbl = tk.Label(row, text=t.ellipsize(name, 50), anchor="w", bg=bg, fg=t.resolve(t.TEXT), bd=0,
                            padx=0, font=t.tk_font(14, s, "bold"))
        name_lbl.grid(row=0, column=1, sticky="sw", pady=(px(14), 0), ipady=px(4))

        line = tk.Frame(row, bg=bg)
        line.grid(row=1, column=1, sticky="w")
        status = entry.get("status")
        if status in STATUSES:
            t.chip(line, f" {status.capitalize()} ", fg_color=t.SURFACE_ALT,
                   text_color=t.STATUS_COLORS[status]).pack(side="left", padx=(0, px(8)))
        text, value = _card_progress(entry, top)
        sub = tk.Label(line, text=text, anchor="w", bg=bg, fg=t.resolve(t.MUTED), bd=0, padx=0,
                       font=t.tk_font(12, s))
        sub.pack(side="left", ipady=px(5))

        bar = _Bar(row, value, height=px(4), bg=t.resolve(t.SURFACE_ALT), fill=t.resolve(t.ACCENT))
        bar.grid(row=2, column=1, sticky="new", pady=(px(6), px(14)))
        self._cards[key] = (_card_shape(key, entry), sub, bar)

        # The whole card (but not its buttons) opens the game's details.
        for widget in (row, thumb, name_lbl, line, sub, bar):
            widget.bind("<Button-1>", lambda _e, k=key: self._open(k))
            widget.configure(cursor="hand2")

        btns = tk.Frame(row, bg=bg)
        btns.grid(row=0, column=2, rowspan=3, padx=px(12))
        exe_path = entry.get("path", "")
        if exe_path:
            t.primary_button(
                btns, "▶  Play", lambda k=key: launch_game(self, self.engine, k, self._reload),
                width=86,
            ).pack(side="left")
        else:
            t.secondary_button(btns, "Locate…", lambda k=key: locate_game(self, self.engine, k, self._reload),
                               width=86).pack(side="left")
        t.danger_button(btns, "Remove", lambda k=key, n=name: self._remove(k, n), width=80).pack(
            side="left", padx=(8, 0)
        )

    def destroy(self) -> None:
        if self._build_job is not None:
            self.after_cancel(self._build_job)
        super().destroy()

    def _open(self, key: str) -> None:
        self.app.show_game(key)

    def _remove(self, key: str, name: str) -> None:
        if remove_game(self, self.engine, key, name):
            self._reload()


def _card_shape(key: str, entry: dict) -> tuple:
    """What a card is built from, apart from the time read: when this changes the
    card has to be built again."""
    return (display_name(key, entry), entry.get("status"), bool(entry.get("path")),
            cached_cover_for_entry(entry), entry.get("vndb_id"))


def _card_progress(entry: dict, top: int) -> tuple[str, float]:
    """A card's "3h 20m read · today · v123" line and progress bar value."""
    seconds = int(entry.get("playtime_seconds", 0))
    bits = [f"{format_playtime(seconds)} read"]
    last = stats.last_played_text(entry.get("last_played"))
    if last:
        bits.append(last)
    if entry.get("vndb_id"):
        bits.append(entry["vndb_id"])
    return "   ·   ".join(bits), seconds / top


class _Bar(tk.Canvas):
    """A thin progress bar (a CTkProgressBar costs as much as all the rest of a card)."""

    def __init__(self, parent, value: float, *, height: int, bg: str, fill: str) -> None:
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self._value, self._fill = value, fill
        self.bind("<Configure>", lambda _e: self._draw_bar())

    def get(self) -> float:
        return self._value

    def set(self, value: float) -> None:
        self._value = value
        self._draw_bar()

    def _draw_bar(self) -> None:
        self.delete("all")
        width = int(self.winfo_width() * max(0.0, min(1.0, self._value)))
        if width > 0:
            self.create_rectangle(0, 0, width, self.winfo_height(), fill=self._fill, width=0)
