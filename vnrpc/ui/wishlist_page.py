from __future__ import annotations

import random
import threading
import time
import tkinter as tk
import webbrowser

import customtkinter as ctk

from ..core import VNRPCEngine
from ..vndb import VNResult
from . import theme as t
from .images import fetch_image_async, make_ctk_image

COVER = (220, 310)
# Coming back to the page after this long fetches the wishlist again.
_STALE_AFTER = 600


def pick_order(wishlist: list[VNResult], skip_ids: set[str], rng: random.Random | None = None) -> list[VNResult]:
    """The wishlist shuffled, VNs already in the Library left out (unless that's
    all of them), so rerolling goes through every VN once before repeating."""
    pool = [vn for vn in wishlist if vn.id not in skip_ids] or list(wishlist)
    (rng or random).shuffle(pool)
    return pool


def length_text(minutes: int) -> str:
    if minutes <= 0:
        return ""
    hours = minutes / 60
    return f"~{hours:.0f}h" if hours >= 2 else f"~{minutes}m" if minutes < 60 else f"~{hours:.1f}h"


class WishlistPage(ctk.CTkFrame):
    """Can't decide what to read next? One VN drawn from the VNDB wishlist.
    Kept between visits, so the current pick is still there when coming back."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.engine: VNRPCEngine = app.engine
        self._order: list[VNResult] = []
        self._pos = -1
        self._total = 0
        self._loaded_at = 0.0
        self._loading = False

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 0))
        t.link_button(top, "←  Library", app.show_library).pack(side="left")

        card = t.card(self)
        card.pack(fill="x", padx=20, pady=(8, 20))
        self.cover = ctk.CTkLabel(card, text="", image=make_ctk_image(None, COVER, radius=10))
        self.cover.pack(side="left", anchor="n", padx=20, pady=20)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 20), pady=20)
        t.overline(info, "RANDOM PICK FROM YOUR VNDB WISHLIST", color=t.ACCENT).pack(fill="x")
        self.title_lbl = ctk.CTkLabel(info, text="", anchor="w", justify="left", font=t.font(24, "bold"),
                                      text_color=t.TEXT)
        self.title_lbl.pack(fill="x", pady=(6, 0))
        self.alt_lbl = t.muted(info, "", justify="left", anchor="w")
        self.alt_lbl.pack(fill="x", pady=(2, 12))
        self.meta = ctk.CTkFrame(info, fg_color="transparent", height=1)
        self.meta.pack(fill="x")
        self.status = t.muted(info, "", size=11, justify="left", anchor="w")
        self.status.pack(fill="x", pady=(12, 0))
        info.bind("<Configure>", lambda e: [lbl.configure(wraplength=max(200, e.width - 10))
                                             for lbl in (self.title_lbl, self.alt_lbl, self.status)])

        btns = ctk.CTkFrame(info, fg_color="transparent")
        btns.pack(side="bottom", fill="x")
        self.next_btn = t.primary_button(btns, "Another one", self._next, width=140)
        self.next_btn.pack(side="left")
        self.vndb_btn = t.secondary_button(btns, "VNDB page ↗", self._open, width=120)
        self.vndb_btn.pack(side="left", padx=(8, 0))
        t.muted(btns, "Space: another one", size=11).pack(side="right")
        self._set_ready(False)

    def on_show(self) -> None:
        if not self._loading and (not self._order or time.time() - self._loaded_at > _STALE_AFTER):
            self._load()

    def on_key(self, event) -> str | None:
        if event.type != tk.EventType.KeyPress:
            return None
        if event.keysym == "Escape":
            self.app.show_library()
            return "break"
        if event.keysym == "space":
            self._next()
            return "break"
        return None

    def _set_ready(self, ready: bool) -> None:
        state = "normal" if ready else "disabled"
        self.next_btn.configure(state=state)
        self.vndb_btn.configure(state=state)

    def _load(self) -> None:
        self._loading = True
        if not self._order:
            self.title_lbl.configure(text="")
            self.status.configure(text="Loading your wishlist…", text_color=t.MUTED)

        def worker() -> None:
            try:
                wishlist, err = self.engine.wishlist(), ""
            except Exception as exc:
                wishlist, err = [], str(exc)
            try:
                self.after(0, lambda: self._loaded(wishlist, err))
            except Exception:
                pass

        threading.Thread(target=worker, name="wishlist", daemon=True).start()

    def _loaded(self, wishlist: list[VNResult], err: str) -> None:
        self._loading = False
        if not self.winfo_exists():
            return
        if err:
            if not self._order:  # keep showing the last pick if only the refresh failed
                self.title_lbl.configure(text="Couldn't load your wishlist")
                self.status.configure(text=err, text_color=t.RED)
            return
        self._loaded_at = time.time()
        if not wishlist:
            self._order = []
            self._set_ready(False)
            self.title_lbl.configure(text="Your wishlist is empty")
            self.status.configure(text="Add VNs to your Wishlist on vndb.org, then come back.", text_color=t.MUTED)
            return
        current = self._current()
        self._order = pick_order(wishlist, self.engine.library_vndb_ids())
        self._total = len(wishlist)
        self._set_ready(True)
        if current is None:
            self._pos = -1
            self._next()
        else:  # a refresh: keep the VN on screen
            ids = [vn.id for vn in self._order]
            self._pos = ids.index(current.id) if current.id in ids else 0
            self._show(self._order[self._pos])

    def _next(self) -> None:
        if not self._order:
            return
        self._pos += 1
        if self._pos >= len(self._order):  # went through all of them: a new round
            self._pos = 0
            last = self._order[-1]
            random.shuffle(self._order)
            if len(self._order) > 1 and self._order[0] is last:
                self._order[0], self._order[1] = self._order[1], self._order[0]
        self._show(self._order[self._pos])

    def _show(self, vn: VNResult) -> None:
        self.title_lbl.configure(text=t.ellipsize(vn.title, 90))
        self.alt_lbl.configure(text=t.ellipsize(vn.alt_title, 90) if vn.alt_title != vn.title else "")
        for w in self.meta.winfo_children():
            w.destroy()
        chips = [vn.year]
        if vn.rating:
            chips.append(f"Rating {vn.rating / 10:.1f}" if vn.rating > 10 else f"Rating {vn.rating:.1f}")
        chips.append(length_text(vn._extra.get("length_minutes", 0)))
        for text in filter(None, chips):
            t.chip(self.meta, f" {text} ", fg_color=t.SURFACE_ALT, text_color=t.MUTED).pack(
                side="left", padx=(0, 6))
        left = len(self._order)
        self.status.configure(
            text=f"{self._pos + 1} / {left} on your wishlist" + (
                "" if left == self._total else f"  ·  {self._total - left} already in your Library skipped"),
            text_color=t.SUBTLE,
        )
        blur = vn.is_nsfw and not self.engine.config["allow_nsfw_covers"]
        self.cover.configure(image=make_ctk_image(None, COVER, radius=10))
        if vn.image_url:
            fetch_image_async(vn.image_url, COVER,
                              lambda img, shown=vn: img and self._current() is shown and self.cover.configure(image=img),
                              widget=self.cover, blur=blur, radius=10)

    def _current(self) -> VNResult | None:
        return self._order[self._pos] if self._order and 0 <= self._pos < len(self._order) else None

    def _open(self) -> None:
        vn = self._current()
        if vn:
            webbrowser.open(vn.vndb_url)
