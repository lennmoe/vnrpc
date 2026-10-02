from __future__ import annotations

import random
import threading
import webbrowser

import customtkinter as ctk

from ..core import VNRPCEngine
from ..vndb import VNResult
from . import theme as t
from .images import fetch_image_async, make_ctk_image

COVER = (180, 254)


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


class WishlistPickDialog(ctk.CTkToplevel):
    """Can't decide what to read next? One VN drawn from the VNDB wishlist."""

    def __init__(self, master, engine: VNRPCEngine) -> None:
        super().__init__(master)
        self.engine = engine
        self._order: list[VNResult] = []
        self._pos = -1
        self._total = 0
        t.setup_window(self, title="Random pick — VNDB wishlist", geometry="560x380", resizable=False,
                       modal_for=master)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<space>", lambda _e: self._next())

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=20)
        self.cover = ctk.CTkLabel(body, text="", image=make_ctk_image(None, COVER, radius=10))
        self.cover.pack(side="left", anchor="n")

        info = ctk.CTkFrame(body, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(18, 0))
        t.overline(info, "TONIGHT YOU READ…", color=t.ACCENT).pack(fill="x")
        self.title_lbl = ctk.CTkLabel(info, text="", anchor="w", justify="left", wraplength=300,
                                      font=t.font(20, "bold"), text_color=t.TEXT)
        self.title_lbl.pack(fill="x", pady=(4, 0))
        self.alt_lbl = t.muted(info, "", wraplength=300, justify="left", anchor="w")
        self.alt_lbl.pack(fill="x", pady=(2, 10))
        self.meta = ctk.CTkFrame(info, fg_color="transparent", height=1)
        self.meta.pack(fill="x")
        self.status = t.muted(info, "Loading your wishlist…", size=11, wraplength=300, justify="left",
                              anchor="w")
        self.status.pack(fill="x", pady=(10, 0))

        btns = ctk.CTkFrame(info, fg_color="transparent")
        btns.pack(side="bottom", fill="x")
        self.next_btn = t.primary_button(btns, "🎲  Another one", self._next, width=150)
        self.next_btn.pack(side="left")
        self.vndb_btn = t.secondary_button(btns, "VNDB page ↗", self._open, width=120)
        self.vndb_btn.pack(side="left", padx=(8, 0))
        self.next_btn.configure(state="disabled")
        self.vndb_btn.configure(state="disabled")

        threading.Thread(target=self._load, name="wishlist", daemon=True).start()

    def _load(self) -> None:
        try:
            wishlist, err = self.engine.wishlist(), ""
        except Exception as exc:
            wishlist, err = [], str(exc)
        try:
            self.after(0, lambda: self._loaded(wishlist, err))
        except Exception:
            pass

    def _loaded(self, wishlist: list[VNResult], err: str) -> None:
        if not self.winfo_exists():
            return
        if err:
            self.title_lbl.configure(text="Couldn't load your wishlist")
            self.status.configure(text=err, text_color=t.RED)
            return
        if not wishlist:
            self.title_lbl.configure(text="Your wishlist is empty")
            self.status.configure(text="Add VNs to your Wishlist on vndb.org and try again.")
            return
        self._order = pick_order(wishlist, self.engine.library_vndb_ids())
        self._total = len(wishlist)
        self.next_btn.configure(state="normal")
        self.vndb_btn.configure(state="normal")
        self._next()

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
        self.title_lbl.configure(text=t.ellipsize(vn.title, 80))
        self.alt_lbl.configure(text=t.ellipsize(vn.alt_title, 80) if vn.alt_title != vn.title else "")
        for w in self.meta.winfo_children():
            w.destroy()
        chips = [vn.year]
        if vn.rating:
            chips.append(f"★ {vn.rating / 10:.1f}" if vn.rating > 10 else f"★ {vn.rating:.1f}")
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
        return self._order[self._pos] if self._order and self._pos >= 0 else None

    def _open(self) -> None:
        vn = self._current()
        if vn:
            webbrowser.open(vn.vndb_url)
