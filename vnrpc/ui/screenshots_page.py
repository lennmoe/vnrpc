from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageTk

from .. import screenshots
from ..core import VNRPCEngine
from ..winapi import copy_image_to_clipboard
from . import theme as t
from .game_page import display_name
from .images import ThumbnailLoader

TILE = (200, 112)
_ALL = "All games"
_BATCH = 60  # tiles built at a time; the rest come with "Show more"


def games_with_shots(engine: VNRPCEngine) -> list[tuple[str, str, list[Path]]]:
    """``(key, name, shots newest first)`` for every VN that has screenshots, the
    most recently captured first."""
    out = []
    for key, entry in engine.config.all_games().items():
        shots = screenshots.list_shots(screenshots.folder_for(engine.config, key))
        if shots:
            out.append((key, display_name(key, entry), shots))
    out.sort(key=lambda g: _mtime(g[2][0]), reverse=True)
    return out


def show_in_folder(path: Path) -> None:
    subprocess.Popen(f'explorer /select,"{path}"')


class ScreenshotsPage(ctk.CTkFrame):
    """Every screenshot of one VN (or of all of them): a big preview with Copy /
    Open / Show in folder / Delete, and the thumbnails down the side."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.engine: VNRPCEngine = app.engine
        self._games: list[tuple[str, str, list[Path]]] = []
        self._shots: list[tuple[str, Path]] = []  # (game key, file) in list order
        self._tiles: dict[Path, ctk.CTkFrame] = {}
        self._shown = 0
        self._index = -1
        self._full: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._loader: ThumbnailLoader | None = None
        self._resize_job = None
        self._names: dict[str, str] = {}
        self._menu_keys: dict[str, str | None] = {}
        self._filter_key: str | None = None
        self._back: Callable[[], None] | None = None

        self._build()
        screenshots.subscribe(self._on_changed)

    def show_for(self, key: str | None = None, select: Path | None = None,
                 back: Callable[[], None] | None = None) -> None:
        """Show the screenshots of game ``key`` (all games if None), ``select`` first.
        ``back``, if given, adds a link back to where the gallery was opened from."""
        self._filter_key = key
        self._back = back
        if back:
            self.top.pack(fill="x", padx=12, pady=(12, 0), before=self.head)
        else:
            self.top.pack_forget()
        self._index = -1
        self._reload(select=select)

    def on_key(self, event) -> str | None:
        if event.type != tk.EventType.KeyPress:
            return None
        ctrl = bool(event.state & 0x4)
        actions = {"Left": lambda: self._step(-1), "Up": lambda: self._step(-1),
                   "Right": lambda: self._step(1), "Down": lambda: self._step(1),
                   "Delete": self._delete, "Return": self._open}
        if ctrl and event.keysym in ("c", "C"):
            self._copy()
        elif event.keysym == "Escape" and self._back:
            self._back()
        elif not ctrl and event.keysym in actions:
            actions[event.keysym]()
        else:
            return None
        return "break"

    def _build(self) -> None:
        self.top = ctk.CTkFrame(self, fg_color="transparent")  # packed only with a "back" link
        t.link_button(self.top, "←  Back", lambda: self._back and self._back()).pack(side="left")
        head = self.head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 10))
        t.page_title(head, "Screenshots").pack(side="left")
        t.secondary_button(head, "Open folder", self._open_folder, width=110, height=30).pack(side="right")
        self.game_menu = t.option_menu(head, [_ALL], command=self._on_menu, width=240,
                                       dynamic_resizing=False)
        self.game_menu.pack(side="right", padx=8)
        self.count_lbl = t.muted(head, "")
        self.count_lbl.pack(side="left", padx=12)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        viewer = t.card(body)
        viewer.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        viewer.grid_columnconfigure(0, weight=1)
        viewer.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewer, highlightthickness=0, bd=0, bg=t.resolve(t.SURFACE_ALT))
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))
        self.canvas.bind("<Configure>", lambda _e: self._schedule_render())
        self.canvas.bind("<Double-Button-1>", lambda _e: self._open())

        info = ctk.CTkFrame(viewer, fg_color="transparent")
        info.grid(row=1, column=0, sticky="ew", padx=16, pady=(10, 14))
        info.grid_columnconfigure(0, weight=1)
        self.title_lbl = ctk.CTkLabel(info, text="", anchor="w", font=t.font(14, "bold"), text_color=t.TEXT)
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.meta_lbl = t.muted(info, "", size=11)
        self.meta_lbl.grid(row=1, column=0, sticky="w")
        actions = self._actions = ctk.CTkFrame(info, fg_color="transparent")
        self._actions_beside: bool | None = None
        viewer.bind("<Configure>", lambda e: self._place_actions(e.width >= 760))
        self.copy_btn = t.primary_button(actions, "Copy", self._copy, width=86)
        self.copy_btn.pack(side="left")
        self.open_btn = t.secondary_button(actions, "Open", self._open, width=70)
        self.open_btn.pack(side="left", padx=(8, 0))
        self.folder_btn = t.secondary_button(actions, "Show in folder", self._show_in_folder, width=120)
        self.folder_btn.pack(side="left", padx=(8, 0))
        self.delete_btn = t.danger_button(actions, "Delete", self._delete, width=76)
        self.delete_btn.pack(side="left", padx=(8, 0))

        self.side = t.scrollable(body, width=TILE[0] + 24)
        self.side.grid(row=0, column=1, sticky="ns")

    def _place_actions(self, beside: bool) -> None:
        """The buttons sit right of the caption, or under it when the viewer is narrow."""
        if beside == self._actions_beside:
            return
        self._actions_beside = beside
        if beside:
            self._actions.grid(row=0, column=1, rowspan=2, sticky="e", pady=0)
        else:
            self._actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _on_menu(self, label: str) -> None:
        self._filter_key = self._menu_keys.get(label)
        self._reload()

    def _reload(self, select: Path | None = None) -> None:
        """Re-read the folders, keeping the selection unless ``select`` is given."""
        current = self._shots[self._index][1] if 0 <= self._index < len(self._shots) else None
        self._games = games_with_shots(self.engine)
        self._names = {key: name for key, name, _ in self._games}
        self._menu_keys = {_ALL: None}
        for key, name, shots in self._games:
            self._menu_keys[self._menu_label(name, shots)] = key
        if self._filter_key and self._filter_key not in self._names:
            # Opened from a VN's page before it has any screenshots: still offer it.
            name = display_name(self._filter_key, self.engine.config.game_override(self._filter_key))
            self._names[self._filter_key] = name
            self._menu_keys[self._menu_label(name, [])] = self._filter_key
        self.game_menu.configure(values=list(self._menu_keys))
        self.game_menu.set(next(lbl for lbl, k in self._menu_keys.items() if k == self._filter_key))

        games = [g for g in self._games if self._filter_key in (None, g[0])]
        self._shots = [(key, path) for key, _name, shots in games for path in shots]
        n = len(self._shots)
        self.count_lbl.configure(text=f"{n} screenshot{'s' if n != 1 else ''}" if n else "")

        wanted = select or current
        paths = [p for _k, p in self._shots]
        self._fill_side(games, upto=max(_BATCH, paths.index(wanted) + 1 if wanted in paths else 0))
        self._select(paths.index(wanted) if wanted in paths else (0 if n else -1))

    def _menu_label(self, name: str, shots: list[Path]) -> str:
        return f"{t.ellipsize(name, 28)}  ({len(shots)})" if shots else t.ellipsize(name, 34)

    def _fill_side(self, games, upto: int) -> None:
        if self._loader:
            self._loader.cancel()
        for w in self.side.winfo_children():
            w.destroy()
        self._tiles.clear()
        if not self._shots:
            return
        grouped = self._filter_key is None and len(games) > 1
        shown = 0
        pending: list[Path] = []
        for key, name, shots in games:
            if shown >= upto:
                break
            if grouped:
                t.overline(self.side, t.ellipsize(name, 26)).pack(fill="x", padx=4, pady=(10 if shown else 2, 4))
            for path in shots:
                if shown >= upto:
                    break
                self._tile(path, shown)
                pending.append(path)
                shown += 1
        self._shown = shown
        if shown < len(self._shots):
            rest = len(self._shots) - shown
            t.secondary_button(self.side, f"Show {min(rest, _BATCH)} more", lambda: self._more(games),
                               height=30).pack(fill="x", padx=4, pady=(6, 8))
        self._loader = ThumbnailLoader(pending, TILE, self._set_thumb, widget=self.side, radius=6)

    def _more(self, games) -> None:
        index = self._index
        self._fill_side(games, upto=self._shown + _BATCH)
        self._highlight(index)

    def _tile(self, path: Path, index: int) -> None:
        tile = ctk.CTkFrame(self.side, fg_color="transparent", border_width=2, border_color=t.BG,
                            corner_radius=9)
        tile.pack(padx=4, pady=3)
        label = ctk.CTkLabel(tile, text="", width=TILE[0], height=TILE[1], fg_color=t.SURFACE_ALT,
                             corner_radius=6)
        label.pack(padx=3, pady=3)
        for w in (tile, label):
            w.bind("<Button-1>", lambda _e, i=index: self._select(i))
            w.bind("<Double-Button-1>", lambda _e, i=index: (self._select(i), self._open()))
            w.configure(cursor="hand2")
        tile._thumb_label = label
        self._tiles[path] = tile

    def _set_thumb(self, index: int, image) -> None:
        if index < len(self._shots):
            tile = self._tiles.get(self._shots[index][1])
            if tile is not None and tile.winfo_exists():
                tile._thumb_label.configure(image=image, fg_color="transparent")

    def _select(self, index: int) -> None:
        self._index = index
        self._full = None
        has = 0 <= index < len(self._shots)
        for btn in (self.copy_btn, self.open_btn, self.folder_btn, self.delete_btn):
            btn.configure(state="normal" if has else "disabled")
        if not has:
            self.title_lbl.configure(text="")
            self.meta_lbl.configure(text="")
            self._render()
            return
        key, path = self._shots[index]
        if index >= self._shown:
            self._more([g for g in self._games if self._filter_key in (None, g[0])])
        self._highlight(index)
        info = screenshots.info(path)
        try:
            with Image.open(path) as im:
                self._full = im.convert("RGB")
        except Exception:
            self._full = None
        bits = [info.taken.strftime("%d %b %Y, %H:%M")]
        if info.width:
            bits.append(f"{info.width}×{info.height}")
        bits.append(path.name)
        game = self._names.get(key, key)
        self.title_lbl.configure(text=t.ellipsize(f"{game}  ·  {info.section}" if info.section else game, 70))
        self.meta_lbl.configure(text="   ·   ".join(bits))
        self._render()

    def _highlight(self, index: int) -> None:
        selected = self._shots[index][1] if 0 <= index < len(self._shots) else None
        for path, tile in self._tiles.items():
            if tile.winfo_exists():
                tile.configure(border_color=t.ACCENT if path == selected else t.BG)
        tile = self._tiles.get(selected)
        if tile is not None:
            self.after(10, lambda: self._scroll_into_view(tile))

    def _scroll_into_view(self, tile) -> None:
        try:
            canvas = self.side._parent_canvas
            region = canvas.bbox("all")
            if not region or not tile.winfo_exists():
                return
            total = region[3] - region[1]
            top = tile.winfo_y()
            view_top, view_h = canvas.canvasy(0), canvas.winfo_height()
            if top < view_top or top + tile.winfo_height() > view_top + view_h:
                canvas.yview_moveto(max(0.0, (top - 12) / max(1, total)))
        except tk.TclError:
            pass

    def _step(self, delta: int) -> None:
        if self._shots:
            self._select(min(max(0, self._index + delta), len(self._shots) - 1))

    def _schedule_render(self) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._render)

    def _render(self) -> None:
        self._resize_job = None
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20:
            return
        if self._full is None:
            if self._shots:
                msg, hint = "Can't open this image", ""
            else:
                msg, hint = "No screenshots yet", screenshots.hotkey_hint(self.engine.config)
            c.create_text(w / 2, h / 2 - 10, text=msg, fill=t.resolve(t.TEXT), font=("Segoe UI", 13, "bold"))
            c.create_text(w / 2, h / 2 + 14, text=hint, fill=t.resolve(t.MUTED), font=("Segoe UI", 10))
            return
        img = self._full
        scale = min(w / img.width, h / img.height, 1.0)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        shown = img if size == img.size else img.resize(size, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown)
        c.create_image(w / 2, h / 2, image=self._photo, anchor="center")

    def _current(self) -> tuple[str, Path] | None:
        return self._shots[self._index] if 0 <= self._index < len(self._shots) else None

    def _copy(self) -> None:
        if self._full is None:
            return
        try:
            copy_image_to_clipboard(self._full)
        except OSError as exc:
            messagebox.showerror("Copy", f"Couldn't copy it: {exc}", parent=self)
            return
        self.copy_btn.configure(text="Copied ✓")
        self.after(1400, lambda: self.copy_btn.winfo_exists() and self.copy_btn.configure(text="Copy"))

    def _open(self) -> None:
        cur = self._current()
        if cur:
            try:
                os.startfile(cur[1])
            except OSError as exc:
                messagebox.showerror("Open", f"Couldn't open it: {exc}", parent=self)

    def _show_in_folder(self) -> None:
        cur = self._current()
        if cur:
            show_in_folder(cur[1])

    def _open_folder(self) -> None:
        cur = self._current()
        folder = cur[1].parent if cur else screenshots.root(self.engine.config)
        if self._filter_key and not cur:
            folder = screenshots.folder_for(self.engine.config, self._filter_key) or folder
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _delete(self) -> None:
        cur = self._current()
        if not cur:
            return
        key, path = cur
        try:
            screenshots.delete(path)
        except OSError as exc:
            messagebox.showerror("Delete", f"Couldn't delete it: {exc}", parent=self)
            return
        index = self._index
        paths = [p for _k, p in self._shots]
        # Keep the same spot in the list: the next one moves up into it.
        after = paths[index + 1] if index + 1 < len(paths) else (paths[index - 1] if index else None)
        self._index = -1
        self._reload(select=after)
        screenshots.notify(key)

    def _on_changed(self, _key: str) -> None:
        if self.winfo_exists() and self.winfo_ismapped():  # hidden: show_for reloads it
            self._reload()

    def destroy(self) -> None:
        screenshots.unsubscribe(self._on_changed)
        if self._loader:
            self._loader.cancel()
        super().destroy()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
