from __future__ import annotations

import datetime as dt
import math
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw, ImageTk

from .. import launcher, screenshots, stats
from ..config import STATUSES
from ..core import VNRPCEngine, format_playtime
from ..covers import cached_cover_for_entry
from . import theme as t
from .images import ThumbnailLoader, load_image

COVER = (96, 136)
WIDTH = 980
LEFT_W = 430  # cover, status, launcher; the stats and chart take the rest
SHOT = (160, 90)
SHOTS_SHOWN = 5
_CHART_FONT = ("Segoe UI", 9)
NO_VOTE = "No rating"
VOTE_CHOICES = [NO_VOTE] + [f"{v / 10:g}" for v in range(100, 9, -5)]  # "10", "9.5" … "1"


def vote_label(vote: int | None) -> str:
    """VNDB's 10-100 vote as it's shown on the site: ``85`` -> ``"8.5"``."""
    return f"{vote / 10:g}" if vote else NO_VOTE


def vote_value(label: str) -> int | None:
    return None if label == NO_VOTE else round(float(label) * 10)


def display_name(key: str, entry: dict) -> str:
    """The user-picked title, else the name last detected in-game, else the key."""
    return entry.get("title") or entry.get("name") or key


def launch_game(parent, engine: VNRPCEngine, key: str, on_change: Callable[[], None]) -> None:
    try:
        launcher.launch(engine.config, engine.config.game_override(key))
    except FileNotFoundError:
        if messagebox.askyesno(
            "Play", "This game's executable can't be found anymore\n"
            "(it may have moved or been uninstalled).\n\nLocate it?", parent=parent,
        ):
            locate_game(parent, engine, key, on_change)
    except launcher.ToolMissing as exc:
        if messagebox.askyesno("Play", f"{exc}\n\nLocate it?", parent=parent) and locate_tool(
                parent, engine, exc.launcher):
            launch_game(parent, engine, key, on_change)
    except OSError as exc:
        messagebox.showerror("Play", f"Couldn't launch it: {exc}", parent=parent)


def locate_tool(parent, engine: VNRPCEngine, which: str) -> bool:
    """Ask where Locale Emulator's LEProc.exe (or NTLEA's ntleas.exe) is; remember it."""
    exe = launcher.TOOL_EXE[which]
    path = filedialog.askopenfilename(
        parent=parent, title=f"Locate {exe} ({launcher.LABELS[which]})",
        filetypes=[(exe, exe), ("Programs", "*.exe")],
    )
    if not path:
        return False
    engine.config[launcher.TOOL_SETTING[which]] = os.path.normpath(path)
    engine.config.save()
    return True


def locate_game(parent, engine: VNRPCEngine, key: str, on_change: Callable[[], None]) -> None:
    path = filedialog.askopenfilename(
        parent=parent, title="Locate the game's executable",
        filetypes=[("Programs", "*.exe"), ("All files", "*.*")],
    )
    if path:
        engine.set_game_path(key, os.path.normpath(path))
        on_change()


def remove_game(parent, engine: VNRPCEngine, key: str, name: str) -> bool:
    if not messagebox.askyesno(
        "Remove", f'Remove "{name}" from the library?\n\n'
        "Its saved playtime, reading history, cover and privacy settings are forgotten.\n"
        "Nothing is uninstalled, and its screenshots are kept.",
        parent=parent,
    ):
        return False
    engine.clear_override(key)
    return True


class GameDialog(ctk.CTkToplevel):
    """One Library game, laid out wide: cover, status and launcher on the left,
    reading stats and a time-read-per-day/week chart on the right, then screenshots."""

    def __init__(self, master, engine: VNRPCEngine, key: str, on_change: Callable[[], None]) -> None:
        super().__init__(master)
        self.engine = engine
        self.key = key
        self._on_change = on_change
        entry = engine.config.game_override(key)
        self.name = display_name(key, entry)
        t.setup_window(self, title=self.name, geometry=f"{WIDTH}x640", minsize=(900, 480), modal_for=master)
        self.bind("<Escape>", lambda _e: self.destroy())

        body = t.scrollable(self)
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="x")
        cols.grid_columnconfigure(0, minsize=LEFT_W)
        cols.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(cols, fg_color="transparent", width=LEFT_W)
        left.grid(row=0, column=0, sticky="nsew")
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        self._build_header(left, entry)
        self._build_status(left, entry)
        self._build_launch(left, entry)
        self._build_stats(right, entry)
        self._build_chart(right, entry)
        self._build_screenshots(body)
        self._build_footer(entry)
        self._fit_height(body)

    def _build_header(self, parent, entry: dict) -> None:
        head = t.card(parent)
        head.pack(fill="x", padx=8, pady=(8, 0))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text="", image=load_image(cached_cover_for_entry(entry), COVER, radius=8)).grid(
            row=0, column=0, rowspan=3, padx=16, pady=16)
        ctk.CTkLabel(head, text=self.name, anchor="w", justify="left", wraplength=LEFT_W - 170,
                     font=t.font(18, "bold"), text_color=t.TEXT).grid(row=0, column=1, sticky="sw", pady=(18, 0),
                                                                     padx=(0, 16))
        path = entry.get("path") or "Executable not located yet"
        t.muted(head, t.ellipsize(path, 42), size=11).grid(row=1, column=1, sticky="w", padx=(0, 16))

        vndb = ctk.CTkFrame(head, fg_color="transparent")
        vndb.grid(row=2, column=1, sticky="nw", pady=(8, 16))
        vn_id, matched = entry.get("vndb_id"), entry.get("matched_vndb_id")
        if vn_id:
            t.secondary_button(vndb, f"VNDB {vn_id} ↗", lambda: webbrowser.open(f"https://vndb.org/{vn_id}"),
                               height=28).pack(side="left")
        elif matched:
            t.secondary_button(vndb, f"VNDB {matched} ↗", lambda: webbrowser.open(f"https://vndb.org/{matched}"),
                               height=28).pack(side="left")
            t.muted(vndb, "found automatically", size=11).pack(side="left", padx=8)
            t.primary_button(vndb, "Confirm", self._confirm_match, width=80, height=28).pack(side="left")
        else:
            t.muted(vndb, "Not matched on VNDB — pick it with “Change cover…” while it runs.",
                    size=11, wraplength=LEFT_W - 170).pack(side="left")

    def _build_status(self, parent, entry: dict) -> None:
        box = t.card(parent)
        box.pack(fill="x", padx=8, pady=(10, 0))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(row, text="Status", font=t.font(13, "bold"), text_color=t.TEXT).pack(side="left")
        self.status = t.segmented(row, [s.capitalize() for s in STATUSES])
        if entry.get("status") in STATUSES:
            self.status.set(entry["status"].capitalize())
        # CTkSegmentedButton ignores clicks on the selected value; route them here so a
        # second click clears the status.
        for value, button in self.status._buttons_dict.items():
            button.configure(command=lambda v=value: self._toggle_status(v))
        self.status.pack(side="right")

        cfg = self.engine.config
        has_token = bool((cfg.get("vndb_token") or "").strip())
        can_rate = has_token and bool(entry.get("vndb_id"))
        rate = ctk.CTkFrame(box, fg_color="transparent")
        rate.pack(fill="x", padx=16, pady=(4, 4))
        ctk.CTkLabel(rate, text="Rating", font=t.font(13, "bold"), text_color=t.TEXT).pack(side="left")
        self._vote = int(entry.get("vndb_vote") or 0) or None
        self.vote_menu = t.option_menu(rate, VOTE_CHOICES, command=self._set_vote, width=120)
        self._show_vote(self._vote)
        self.vote_menu.pack(side="right")
        self.vote_state = t.muted(rate, "", size=11)
        self.vote_state.pack(side="right", padx=8)

        if not has_token:
            note = "Add your VNDB token in Settings to rate it and sync its status to your VNDB list."
        elif not entry.get("vndb_id"):
            note = "Confirm the VNDB match above to rate it and sync it to your VNDB list."
        elif cfg.get("vndb_sync"):
            note = "Status and rating are sent to your VNDB list."
        else:
            note = "The rating is sent to your VNDB list. Turn on list sync in Settings for the status too."
        t.muted(box, note, size=11, wraplength=LEFT_W - 60).pack(fill="x", padx=16, pady=(0, 12))
        if can_rate:
            self._load_vote()
        else:
            self.vote_menu.configure(state="disabled")

    def _show_vote(self, vote: int | None) -> None:
        label = vote_label(vote)
        if label not in VOTE_CHOICES:  # e.g. 8.3, given on the website
            self.vote_menu.configure(values=VOTE_CHOICES[:1] + sorted(
                VOTE_CHOICES[1:] + [label], key=float, reverse=True))
        self.vote_menu.set(label)

    def _in_background(self, work, done) -> None:
        """Run ``work()`` off the UI thread, then ``done(result, error)`` on it."""
        def worker() -> None:
            try:
                result, error = work(), None
            except Exception as exc:
                result, error = None, exc
            try:
                self.after(0, lambda: self.winfo_exists() and done(result, error))
            except Exception:  # closed meanwhile
                pass

        threading.Thread(target=worker, name="vndb-vote", daemon=True).start()

    def _load_vote(self) -> None:
        self.vote_state.configure(text="Checking VNDB…", text_color=t.MUTED)

        def done(vote, error) -> None:
            if error is not None:
                self.vote_state.configure(text=t.ellipsize(str(error).capitalize(), 34),
                                          text_color=t.SUBTLE)
                return
            self._vote = vote
            self._show_vote(vote)
            self.vote_state.configure(text="")

        self._in_background(lambda: self.engine.vndb_vote(self.key), done)

    def _set_vote(self, label: str) -> None:
        vote = vote_value(label)
        if vote == self._vote:
            return
        self.vote_menu.configure(state="disabled")
        self.vote_state.configure(text="Saving…", text_color=t.MUTED)

        def done(_result, error) -> None:
            self.vote_menu.configure(state="normal")
            if error is not None:
                self._show_vote(self._vote)  # put back what VNDB still has
                self.vote_state.configure(text=t.ellipsize(str(error).capitalize(), 34),
                                          text_color=t.RED)
                return
            self._vote = vote
            self.vote_state.configure(text="Saved on VNDB ✓", text_color=t.GREEN)
            self._on_change()

        self._in_background(lambda: self.engine.set_vndb_vote(self.key, vote), done)

    def _build_launch(self, parent, entry: dict) -> None:
        box = t.card(parent)
        box.pack(fill="x", padx=8, pady=(10, 0))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(row, text="Launch with", font=t.font(13, "bold"), text_color=t.TEXT).pack(side="left")
        self._launcher = entry.get("launcher") if entry.get("launcher") in launcher.LAUNCHERS else launcher.NORMAL
        self.launch_with = t.segmented(row, [launcher.LABELS[k] for k in launcher.LAUNCHERS],
                                       command=self._set_launcher)
        self.launch_with.set(launcher.LABELS[self._launcher])
        self.launch_with.pack(side="right")
        self.launch_note = t.muted(box, "", size=11, wraplength=LEFT_W - 60)
        self.launch_note.pack(fill="x", padx=16, pady=(0, 12))
        self._show_launch_note()

    def _show_launch_note(self) -> None:
        if self._launcher == launcher.NORMAL:
            note = ("For Japanese VNs with garbled text or that won't start: Play can go through "
                    "Locale Emulator or NTLEA.")
        else:
            tool = launcher.tool_path(self.engine.config, self._launcher)
            exe = launcher.TOOL_EXE[self._launcher]
            note = (f"Play starts it through {t.ellipsize(tool, 42)}." if tool else
                    f"{exe} can't be found anymore — Play will ask where it is.")
        self.launch_note.configure(text=note)

    def _set_launcher(self, label: str) -> None:
        which = next(k for k in launcher.LAUNCHERS if launcher.LABELS[k] == label)
        if (which != launcher.NORMAL and not launcher.tool_path(self.engine.config, which)
                and not locate_tool(self, self.engine, which)):
            self.launch_with.set(launcher.LABELS[self._launcher])  # cancelled: keep the old choice
            return
        self._launcher = which
        self.engine.config.set_game_override(self.key, launcher=which)
        self._show_launch_note()
        self._on_change()

    def _build_stats(self, parent, entry: dict) -> None:
        daily = entry.get("daily") or {}
        tiles = ctk.CTkFrame(parent, fg_color="transparent")
        tiles.pack(fill="x", padx=8, pady=(8, 0))
        values = (
            ("Total read", format_playtime(int(entry.get("playtime_seconds", 0)))),
            ("This week", format_playtime(stats.this_week_seconds(daily))),
            ("Sessions", str(int(entry.get("sessions", 0))) if entry.get("sessions") else "—"),
            ("Last played", stats.last_played_text(entry.get("last_played")) or "—"),
        )
        for col, (label, value) in enumerate(values):
            tiles.grid_columnconfigure(col, weight=1, uniform="tile")
            tile = t.card(tiles, corner_radius=10)
            tile.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 0 if col == 3 else 5))
            t.overline(tile, label).pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(tile, text=value, anchor="w", font=t.font(17, "bold"), text_color=t.TEXT).pack(
                fill="x", padx=12, pady=(0, 10))

    def _build_screenshots(self, parent) -> None:
        self._shots_box = t.card(parent)
        self._shots_box.pack(fill="x", padx=8, pady=(10, 8))
        self._shots_loader: ThumbnailLoader | None = None
        self._fill_screenshots()
        screenshots.subscribe(self._on_screenshots_changed)

    def _fill_screenshots(self) -> None:
        box = self._shots_box
        for w in box.winfo_children():
            w.destroy()
        if self._shots_loader:
            self._shots_loader.cancel()
        shots = screenshots.list_shots(screenshots.folder_for(self.engine.config, self.key))

        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(head, text="Screenshots", font=t.font(13, "bold"), text_color=t.TEXT).pack(side="left")
        if not shots:
            t.muted(box, screenshots.hotkey_hint(self.engine.config), size=11).pack(fill="x", padx=16,
                                                                                    pady=(0, 12))
            return
        t.muted(head, str(len(shots)), size=12).pack(side="left", padx=8)
        t.secondary_button(head, "View all", lambda: self._open_gallery(), width=90, height=28).pack(side="right")

        strip = ctk.CTkFrame(box, fg_color="transparent")
        strip.pack(fill="x", padx=12, pady=(0, 12))
        labels = []
        for i, path in enumerate(shots[:SHOTS_SHOWN]):
            lbl = ctk.CTkLabel(strip, text="", width=SHOT[0], height=SHOT[1], fg_color=t.SURFACE_ALT,
                               corner_radius=6, cursor="hand2")
            lbl.grid(row=0, column=i, padx=4)
            lbl.bind("<Button-1>", lambda _e, p=path: self._open_gallery(p))
            labels.append(lbl)
        self._shots_loader = ThumbnailLoader(
            shots[:SHOTS_SHOWN], SHOT, lambda i, img: labels[i].configure(image=img, fg_color="transparent"),
            widget=strip, radius=6,
        )

    def _open_gallery(self, select=None) -> None:
        from .screenshots_dialog import ScreenshotsDialog  # it imports this module

        ScreenshotsDialog(self, self.engine, key=self.key, select=select)

    def _on_screenshots_changed(self, key: str) -> None:
        if key == self.key and self.winfo_exists():
            self._fill_screenshots()

    def _build_chart(self, parent, entry: dict) -> None:
        self._daily = entry.get("daily") or {}
        box = t.card(parent)
        box.pack(fill="x", padx=8, pady=(10, 0))
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(head, text="Time read", font=t.font(13, "bold"), text_color=t.TEXT).pack(side="left")
        self.range = t.segmented(head, ["30 days", "12 weeks"], command=lambda _v: self._fill_chart())
        self.range.set("30 days")
        self.range.pack(side="right")
        self.chart = ReadingChart(box)
        self.chart.pack(fill="x", padx=12, pady=(4, 4))
        since = stats.first_day(self._daily)
        note = (f"History since {stats.short_date(since)}. Time read before that only counts in the total."
                if since else "History fills in as you read — time read before this update only counts "
                              "in the total.")
        t.muted(box, note, size=11, wraplength=WIDTH - LEFT_W - 80).pack(fill="x", padx=16, pady=(0, 12))
        self._fill_chart()

    def _fill_chart(self) -> None:
        today = dt.date.today()
        if self.range.get() == "12 weeks":
            series = stats.weekly_series(self._daily, 12, today)
            points = [(stats.short_date(monday, today), f"Week of {stats.short_date(monday, today)}", secs)
                      for monday, secs in series]
        else:
            series = stats.daily_series(self._daily, 30, today)
            points = [(stats.short_date(day, today), f"{day.strftime('%a')} {stats.short_date(day, today)}", secs)
                      for day, secs in series]
        # Label every Nth column counting back from today, so the newest one is always labelled.
        step = 3 if self.range.get() == "12 weeks" else 7
        points = [(axis if (len(points) - 1 - i) % step == 0 else "", tip, secs)
                  for i, (axis, tip, secs) in enumerate(points)]
        self.chart.set_data(points)

    def _build_footer(self, entry: dict) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(8, 16))
        exe_path = entry.get("path", "")
        if exe_path:
            t.primary_button(bar, "▶  Play", lambda: launch_game(self, self.engine, self.key, self._changed),
                             width=96).pack(side="left")
        else:
            t.secondary_button(bar, "Locate…", lambda: locate_game(self, self.engine, self.key, self._reopen),
                               width=96).pack(side="left")
        t.danger_button(bar, "Remove", self._remove, width=90).pack(side="left", padx=8)
        t.secondary_button(bar, "Close", self.destroy, width=90).pack(side="right")

    def _fit_height(self, body) -> None:
        """Open tall enough to show everything without scrolling, when the screen allows."""
        self.update_idletasks()
        chrome = self.winfo_reqheight() - body._parent_canvas.winfo_reqheight()
        wanted = body.winfo_reqheight() + chrome + 16
        height = min(wanted, self.winfo_screenheight() - 80)
        self.geometry(f"{WIDTH}x{height}")

    def _changed(self) -> None:
        self._on_change()

    def _reopen(self) -> None:
        """Rebuild with fresh data (after something that changes the header or footer)."""
        self._on_change()
        master = self.master
        self.destroy()
        GameDialog(master, self.engine, self.key, self._on_change)

    def _toggle_status(self, value: str) -> None:
        if self.status.get() == value:
            self.status.set("")  # a value that isn't a button unselects them all
            self.engine.set_game_status(self.key, "")
        else:
            self.status.set(value)
            self.engine.set_game_status(self.key, value.lower())
        self._on_change()

    def _confirm_match(self) -> None:
        self.engine.confirm_vn_match(self.key)
        self._reopen()

    def _remove(self) -> None:
        if remove_game(self, self.engine, self.key, self.name):
            self._on_change()
            self.destroy()

    def destroy(self) -> None:
        screenshots.unsubscribe(self._on_screenshots_changed)
        super().destroy()


class ReadingChart(ctk.CTkFrame):
    """Column chart of time read per day or per week. One series, so no legend: the
    card title names it. Hovering a column shows its exact date and duration."""

    PAD_L, PAD_R, PAD_T, PAD_B = 52, 8, 18, 22
    MAX_BAR = 24
    RADIUS = 4

    def __init__(self, parent, height: int = 180) -> None:
        super().__init__(parent, fg_color="transparent")
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0, bg=t.resolve(t.SURFACE))
        self.canvas.pack(fill="x", expand=True)
        self._points: list[tuple[str, str, int]] = []
        self._slots: list[tuple[float, float]] = []
        self._hover = -1
        self._bars: ImageTk.PhotoImage | None = None
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(-1))

    def set_data(self, points: list[tuple[str, str, int]]) -> None:
        """``points``: ``(axis label or "", tooltip title, seconds)``, oldest first."""
        self._points = points
        self._hover = -1
        self._redraw()

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or not self._points:
            return
        grid, text = t.resolve(t.BORDER), t.resolve(t.MUTED)
        left, right, top, base = self.PAD_L, w - self.PAD_R, self.PAD_T, h - self.PAD_B
        peak = max(secs for _, _, secs in self._points)
        step = _tick_step(peak)
        ceiling = max(step, math.ceil(peak / step) * step) if peak else step

        for i in range(int(ceiling // step) + 1):
            y = base - (base - top) * (i * step) / ceiling
            c.create_line(left, y, right, y, fill=grid, width=1, tags="grid")
            c.create_text(left - 6, y, text=_duration(i * step), anchor="e", fill=text, font=_CHART_FONT)

        n = len(self._points)
        slot = (right - left) / n
        bar = max(2.0, min(self.MAX_BAR, slot - 2))
        self._slots = []
        peak_index = max(range(n), key=lambda i: self._points[i][2]) if peak else -1
        columns = []
        for i, (axis, _tip, secs) in enumerate(self._points):
            x0 = left + i * slot
            self._slots.append((x0, x0 + slot))
            cx = x0 + slot / 2
            if axis:
                label = c.create_text(cx, base + 12, text=axis, fill=text, font=_CHART_FONT)
                x0, _y0, x1, _y1 = c.bbox(label)
                if x1 > w - 1:  # keep the newest date inside the chart
                    c.move(label, w - 1 - x1, 0)
                elif x0 < 0:
                    c.move(label, -x0, 0)
            if secs <= 0:
                continue
            y = base - (base - top) * secs / ceiling
            columns.append((cx - bar / 2, y, cx + bar / 2, base,
                            t.resolve(t.ACCENT_HOVER if i == self._hover else t.ACCENT)))
            if i == peak_index:
                c.create_text(cx, y - 7, text=_duration(secs), fill=t.resolve(t.TEXT), font=_CHART_FONT)

        if columns:
            self._bars = ImageTk.PhotoImage(_columns_image(w, h, columns, self.RADIUS, t.resolve(t.ACCENT)))
            c.tag_raise(c.create_image(0, 0, image=self._bars, anchor="nw"), "grid")  # over the grid, under text
        if not peak:
            c.create_text((left + right) / 2, (top + base) / 2, text="Nothing read in this period",
                          fill=text, font=_CHART_FONT)
        if 0 <= self._hover < n:
            self._draw_tooltip(self._hover)

    def _draw_tooltip(self, i: int) -> None:
        c = self.canvas
        _axis, title, secs = self._points[i]
        label = f"{title}  ·  {_duration(secs, exact=True) if secs else 'nothing read'}"
        x0, x1 = self._slots[i]
        txt = c.create_text(0, 0, text=label, anchor="nw", fill=t.resolve(t.TEXT), font=_CHART_FONT)
        bx0, by0, bx1, by1 = c.bbox(txt)
        tw, th = bx1 - bx0 + 16, by1 - by0 + 10
        x = min(max(4, (x0 + x1) / 2 - tw / 2), c.winfo_width() - tw - 4)
        y = 2
        box = c.create_rectangle(x, y, x + tw, y + th, fill=t.resolve(t.SURFACE_HOVER),
                                 outline=t.resolve(t.BORDER))
        c.coords(txt, x + 8, y + 5)
        c.tag_raise(txt, box)

    def _on_motion(self, event) -> None:
        hit = next((i for i, (x0, x1) in enumerate(self._slots) if x0 <= event.x < x1), -1)
        self._set_hover(hit)

    def _set_hover(self, index: int) -> None:
        if index != self._hover:
            self._hover = index
            self._redraw()


_TICK_STEPS = tuple(m * 60 for m in (5, 10, 15, 30, 60, 120, 180, 240, 360, 480, 720, 1440))


def _tick_step(peak: int) -> int:
    """The smallest clean step (5 min … 24 h) that fits ``peak`` in at most 4 gridlines."""
    for step in _TICK_STEPS:
        if peak <= step * 4:
            return step
    return _TICK_STEPS[-1] * max(1, math.ceil(peak / (_TICK_STEPS[-1] * 4)))


def _duration(seconds: int, *, exact: bool = False) -> str:
    """Axis form (``"2h"``, ``"30m"``, ``"1h 30m"``) or, with ``exact``, ``"1h 07m"``."""
    minutes = int(seconds) // 60
    hours, mins = divmod(minutes, 60)
    if exact:
        return format_playtime(seconds) if hours else f"{mins}m"
    if hours and mins:
        return f"{hours}h {mins}m"
    return f"{hours}h" if hours else f"{mins}m"


_SUPERSAMPLE = 3


def _columns_image(w: int, h: int, columns, radius: int, base_color: str) -> Image.Image:
    """The chart's columns, smooth-edged: rounded top (the data end), square foot on
    the baseline. Drawn at ``_SUPERSAMPLE``x and shrunk, since Tk canvas shapes
    aren't anti-aliased. ``columns``: ``(x0, y0, x1, y1, color)`` in canvas pixels."""
    s = _SUPERSAMPLE
    # Transparent pixels carry the bar color, so shrinking doesn't leave dark fringes.
    img = Image.new("RGBA", (w * s, h * s), ImageColor.getrgb(base_color) + (0,))
    draw = ImageDraw.Draw(img)
    for x0, y0, x1, y1, color in columns:
        box = [round(x0 * s), round(y0 * s), round(x1 * s) - 1, round(y1 * s) - 1]
        r = min(radius, (x1 - x0) / 2, y1 - y0)
        if r >= 1:
            draw.rounded_rectangle(box, radius=round(r * s), fill=color, corners=(True, True, False, False))
        else:
            draw.rectangle(box, fill=color)
    return img.resize((w, h), Image.LANCZOS)
