from __future__ import annotations

import datetime as dt
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from .. import share_card
from ..core import VNRPCEngine
from ..engines import is_blacklisted
from ..winapi import copy_image_to_clipboard
from . import theme as t

PREVIEW = (768, 432)
_PALETTE = ("BG", "SURFACE", "SURFACE_ALT", "BORDER", "TEXT", "MUTED", "SUBTLE", "ACCENT", "GREEN")


class ShareCardDialog(ctk.CTkToplevel):
    """Makes the "My week / month in visual novels" image, to copy into Discord."""

    def __init__(self, master, engine: VNRPCEngine) -> None:
        super().__init__(master)
        self.engine = engine
        self._card: Image.Image | None = None
        self._job = 0
        t.setup_window(self, title="Share your reading", geometry="820x580", minsize=(820, 580),
                       modal_for=master)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-c>", lambda _e: self._copy())

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(18, 12))
        ctk.CTkLabel(head, text="Share your reading", font=t.font(20, "bold"), text_color=t.TEXT).pack(
            side="left")
        labels = [share_card.PERIOD_LABELS[k] for k in share_card.PERIODS]
        self.period = t.segmented(head, labels, command=lambda _v: self._render())
        self.period.set(labels[0])
        self.period.pack(side="right")

        frame = ctk.CTkFrame(self, fg_color="transparent", border_width=1, border_color=t.BORDER,
                             corner_radius=0)
        frame.pack(padx=24)
        self.preview = ctk.CTkLabel(frame, text="Drawing…", width=PREVIEW[0], height=PREVIEW[1],
                                    fg_color="transparent", text_color=t.MUTED, font=t.font(13))
        self.preview.pack(padx=1, pady=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(14, 18))
        self.copy_btn = t.primary_button(bar, "Copy image", self._copy, width=130)
        self.copy_btn.pack(side="left")
        t.secondary_button(bar, "Save…", self._save, width=90).pack(side="left", padx=8)
        t.muted(bar, "Then paste it in a Discord message with Ctrl+V.", size=12).pack(side="left", padx=8)
        t.secondary_button(bar, "Close", self.destroy, width=90).pack(side="right")

        self._render()

    def _kind(self) -> str:
        label = self.period.get()
        return next(k for k, v in share_card.PERIOD_LABELS.items() if v == label)

    def _render(self) -> None:
        self._job += 1
        job, kind = self._job, self._kind()
        palette = {name: t.resolve(getattr(t, name)) for name in _PALETTE}
        allow_nsfw = bool(self.engine.config["allow_nsfw_covers"])
        self.copy_btn.configure(state="disabled")

        def worker() -> None:
            data = share_card.collect(self._games(), kind, dt.date.today())
            if not allow_nsfw:
                self._learn_nsfw(data)
            card = share_card.render(data, palette, allow_nsfw=allow_nsfw)
            try:
                self.after(0, lambda: self._show(job, card))
            except Exception:  # closed meanwhile
                pass

        threading.Thread(target=worker, name="share-card", daemon=True).start()

    def _games(self) -> dict[str, dict]:
        blacklist = self.engine.blacklist
        return {key: entry for key, entry in self.engine.config.all_games().items()
                if not is_blacklisted(entry.get("path") or key.split("@", 1)[0], blacklist)}

    def _learn_nsfw(self, data: share_card.CardData) -> None:
        """VNs not run since covers started being flagged: ask VNDB, so a flagged
        cover still gets blurred. Offline, they're shown as they are."""
        for vn in data.vns[:share_card.MAX_COVERS]:
            entry = self.engine.config.game_override(vn.key)
            vn_id = entry.get("vndb_id") or entry.get("matched_vndb_id")
            if "cover_nsfw" in entry or not vn_id or entry.get("cover_source") in ("local", "url"):
                continue
            try:
                result = self.engine.vndb.get_vn(vn_id)
            except Exception:
                continue
            if result is not None:
                vn.nsfw = result.is_nsfw
                self.engine.config.set_game_override(vn.key, cover_nsfw=result.is_nsfw)

    def _show(self, job: int, card: Image.Image) -> None:
        if job != self._job or not self.winfo_exists():
            return
        self._card = card
        self.preview.configure(text="", image=ctk.CTkImage(light_image=card, dark_image=card, size=PREVIEW))
        self.copy_btn.configure(state="normal")

    def _copy(self) -> None:
        if self._card is None:
            return
        try:
            copy_image_to_clipboard(self._card)
        except OSError as exc:
            messagebox.showerror("Copy", f"Couldn't copy it: {exc}", parent=self)
            return
        self.copy_btn.configure(text="Copied ✓")
        self.after(1400, lambda: self.copy_btn.winfo_exists() and self.copy_btn.configure(text="Copy image"))

    def _save(self) -> None:
        if self._card is None:
            return
        name = f"{self.period.get().lower().replace(' ', '-')}-{dt.date.today().isoformat()}.png"
        path = filedialog.asksaveasfilename(parent=self, title="Save the card", initialfile=f"vn-{name}",
                                            defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if path:
            try:
                self._card.save(path, "PNG")
            except OSError as exc:
                messagebox.showerror("Save", f"Couldn't save it: {exc}", parent=self)
