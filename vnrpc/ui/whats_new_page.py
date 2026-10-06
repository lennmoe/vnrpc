from __future__ import annotations

import threading
import tkinter as tk
import webbrowser

import customtkinter as ctk

from .. import __version__, release_notes
from ..release_notes import Line, Notes
from . import theme as t


class WhatsNewPage(ctk.CTkFrame):
    """The release notes of what was just installed (shown once after an update),
    or of the last few versions (Settings → App → What's new)."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._gen = 0

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 4))
        t.page_title(head, "What's new").pack(side="left")
        t.primary_button(head, "Got it", app.show_home, width=100).pack(side="right")
        t.link_button(head, "All releases on GitHub ↗", lambda: webbrowser.open(release_notes.RELEASES_PAGE)).pack(
            side="right", padx=8)
        self.sub = t.muted(self, "")
        self.sub.pack(fill="x", padx=20, pady=(0, 10))

        card = t.card(self)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        s = ctk.ScalingTracker.get_widget_scaling(self)
        bg = t.resolve(t.SURFACE)
        # A plain Text: it wraps and scrolls long notes by itself, and styles runs of text.
        self.text = tk.Text(card, wrap="word", bd=0, highlightthickness=0, bg=bg, fg=t.resolve(t.TEXT),
                            font=t.tk_font(13, s), padx=round(20 * s), pady=round(14 * s), cursor="arrow",
                            spacing1=round(2 * s), spacing3=round(2 * s), insertwidth=0)
        self.text.pack(fill="both", expand=True, padx=2, pady=2)
        px = lambda v: round(v * s)  # noqa: E731
        self.text.tag_configure("version", font=t.tk_font(19, s, "bold"), foreground=t.resolve(t.ACCENT),
                                spacing1=px(10), spacing3=px(2))
        self.text.tag_configure("date", foreground=t.resolve(t.MUTED), font=t.tk_font(12, s), spacing3=px(6))
        self.text.tag_configure("h1", font=t.tk_font(16, s, "bold"), spacing1=px(12), spacing3=px(4))
        self.text.tag_configure("h2", font=t.tk_font(15, s, "bold"), spacing1=px(12), spacing3=px(4))
        self.text.tag_configure("h3", font=t.tk_font(13, s, "bold"), spacing1=px(8), spacing3=px(2))
        self.text.tag_configure("bold", font=t.tk_font(13, s, "bold"))
        self.text.tag_configure("muted", foreground=t.resolve(t.MUTED))
        self.text.tag_configure("rule", font=t.tk_font(6, s), spacing1=px(10), spacing3=px(6))
        self.text.tag_configure("gap", font=t.tk_font(4, s), spacing1=0, spacing3=0)  # a blank Markdown line
        for level in range(4):
            first, rest = px(8 + 22 * level), px(8 + 22 * level + 16)
            self.text.tag_configure(f"bullet{level}", lmargin1=first, lmargin2=rest, spacing1=px(3))
        self.text.configure(state="disabled")

    def on_key(self, event) -> str | None:
        if event.keysym == "Escape" and event.type == tk.EventType.KeyPress:
            self.app.show_home()
            return "break"
        return None

    def load(self, since: str | None = None, recent: int = 0) -> None:
        """Show the notes after version ``since`` up to this one (just this one when
        None), or the last ``recent`` versions'."""
        self._gen += 1
        gen = self._gen
        self.sub.configure(text="Loading the release notes…")
        self._write([])

        def worker() -> None:
            try:
                notes, err = release_notes.pick(release_notes.fetch(), __version__, since, recent), ""
            except Exception as exc:
                notes, err = [], str(exc) or type(exc).__name__
            try:
                self.after(0, lambda: gen == self._gen and self.winfo_exists() and self._show(notes, err, since))
            except Exception:
                pass

        threading.Thread(target=worker, name="release-notes", daemon=True).start()

    def _show(self, notes: list[Notes], err: str, since: str | None) -> None:
        if err:
            self.sub.configure(text="Couldn't load the release notes (are you offline?). "
                                    "They're on GitHub too: “All releases on GitHub”.")
            return
        if not notes:
            self.sub.configure(text=f"You're on version {__version__}. No release notes were found for it.")
            return
        if since and len(notes) > 1:
            self.sub.configure(text=f"Updated from {since} to {__version__}. Here's everything that changed.")
        elif since or len(notes) == 1:
            self.sub.configure(text=f"You're now on version {__version__}.")
        else:
            self.sub.configure(text=f"You're on version {__version__}. The latest releases:")
        self._write(notes)

    def _write(self, notes: list[Notes]) -> None:
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        for i, note in enumerate(notes):
            if i:
                text.insert("end", "\n", "rule")
            text.insert("end", f"Version {note.version}\n", "version")
            if note.date:
                text.insert("end", f"{note.date}\n", "date")
            for line in release_notes.parse(note.body) or [Line("text", [("No details for this one.", False)])]:
                self._insert(line)
        text.configure(state="disabled")
        text.yview_moveto(0)

    def _insert(self, line: Line) -> None:
        text = self.text
        if line.kind == "blank":
            text.insert("end", "\n", "gap")
            return
        block = f"bullet{min(line.level, 3)}" if line.kind == "bullet" else line.kind
        if line.kind == "bullet":
            text.insert("end", "•  " if line.level == 0 else "◦  ", (block, "muted"))
        for piece, bold in line.parts:
            text.insert("end", piece, (block, "bold") if bold and line.kind in ("text", "bullet") else (block,))
        text.insert("end", "\n", (block,))
