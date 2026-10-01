from __future__ import annotations

import json
import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import __version__, autostart, backup, hotkey, launcher, screenshots, updater
from ..config import DEFAULTS
from ..core import VNRPCEngine
from ..engines import normalize_exe
from . import theme as t
from .theme_editor import ThemeTab


class SettingsPage(ctk.CTkFrame):
    """Built afresh each time it's shown, so it never saves stale values over changes
    made meanwhile (e.g. "Not a VN" adding to the blacklist)."""

    def __init__(self, master, app, tab: str | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.engine: VNRPCEngine = app.engine
        self.cfg = self.engine.config
        self._listening = False

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 4))
        t.page_title(head, "Settings").pack(side="left")
        self.save_btn = t.primary_button(head, "Save", self._save, width=110)
        self.save_btn.pack(side="right")

        tabs = ctk.CTkTabview(
            self, fg_color=t.SURFACE, border_width=1, border_color=t.BORDER, corner_radius=t.RADIUS,
            segmented_button_fg_color=t.SURFACE_ALT, segmented_button_selected_color=t.SELECTED,
            segmented_button_selected_hover_color=t.SELECTED_HOVER,
            segmented_button_unselected_color=t.SURFACE_ALT,
            segmented_button_unselected_hover_color=t.SURFACE_HOVER, text_color=t.TEXT,
        )
        tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.tabs = tabs
        self._build_general(tabs.add("General"))
        self.theme_tab = ThemeTab(tabs.add("Theme"), self.cfg)
        self.theme_tab.pack(fill="both", expand=True)
        self._build_rules(tabs.add("Title rules"))
        self._build_blacklist(tabs.add("Blacklist"))
        if tab:
            tabs.set(tab)

    def _build_general(self, tab) -> None:
        frame = t.scrollable(tab)
        frame.pack(fill="both", expand=True)

        _section(frame, "Discord")
        t.muted(frame, "Application ID", size=12).pack(fill="x", padx=16)
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 0))
        self.client_id = t.entry(row)
        self.client_id.insert(0, str(self.cfg["discord_client_id"]))
        self.client_id.pack(side="left", fill="x", expand=True, padx=(0, 8))
        t.secondary_button(row, "Test", self._test_connection, width=70).pack(side="left")
        self.test_lbl = t.muted(frame, "", size=11)
        self._hint_anchor = t.muted(
            frame,
            "Create one at discord.com/developers → New Application, then paste its "
            "Application ID. No bot or OAuth needed.",
            size=11, wraplength=480,
        )
        self._hint_anchor.pack(fill="x", padx=16, pady=(6, 4))

        _section(frame, "Presence")
        self.show_section = t.switch(
            frame, "Show where you are in the story", self.cfg.get("show_section", True),
            hint='The "Reading — Chapter 1" line.',
        )
        self.show_total_read = t.switch(
            frame, "Show total time read", self.cfg.get("show_total_read", True),
            hint='The "Total read: 3h 40m" line.',
        )
        self.show_elapsed = t.switch(frame, "Show elapsed time", self.cfg["show_elapsed"])
        self.clear_on_close = t.switch(frame, "Clear presence when the VN closes", self.cfg["clear_on_close"])
        self.show_vndb_button = t.switch(frame, 'Add a "View on VNDB" button', self.cfg["show_vndb_button"])
        self.idle_when_unfocused = t.switch(
            frame, "Go idle when the VN isn't the active window", bool(self.cfg.get("idle_when_unfocused")),
            hint="Clears your Discord status and stops the elapsed time and the time read "
                 "until you go back to the game.",
        )
        self.idle_seconds = _field(frame, "Seconds in the background before going idle",
                                   str(self.cfg.get("idle_seconds", DEFAULTS["idle_seconds"])), width=70)

        _section(frame, "Covers & matching")
        self.allow_nsfw = t.switch(
            frame, "Allow NSFW-flagged covers", self.cfg["allow_nsfw_covers"],
            hint="Off: flagged covers are blurred here and replaced by the fallback image on Discord.",
        )
        self.use_steam_names = t.switch(
            frame, "Use Steam library names", self.cfg["use_steam_names"],
            hint="Gives much better VNDB matches for games installed through Steam.",
        )

        _section(frame, "VNDB list")
        t.muted(frame, "Personal token", size=12).pack(fill="x", padx=16)
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 0))
        self.vndb_token = t.entry(row, show="•")
        self.vndb_token.insert(0, str(self.cfg.get("vndb_token") or ""))
        self.vndb_token.pack(side="left", fill="x", expand=True, padx=(0, 8))
        t.secondary_button(row, "Test", self._test_vndb_token, width=70).pack(side="left")
        self.vndb_test_lbl = t.muted(frame, "", size=11)
        self._vndb_hint = t.muted(
            frame,
            "vndb.org → your profile → Edit → Applications → New token, with access to your "
            "list and permission to edit it.",
            size=11, wraplength=480,
        )
        self._vndb_hint.pack(fill="x", padx=16, pady=(6, 4))
        self.vndb_sync = t.switch(
            frame, "Sync reading status to my VNDB list", bool(self.cfg.get("vndb_sync")),
            hint="VNs you start are marked Playing, and statuses set in the Library are sent too. "
                 "Only VNs whose VNDB entry you picked or confirmed are synced.",
        )

        _section(frame, "Screenshots")
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text="Capture key", font=t.font(13), text_color=t.TEXT).pack(side="left")
        self._hotkey_value = hotkey.normalize(self.cfg.get("screenshot_hotkey"))
        self.hotkey_btn = t.secondary_button(row, "", self._listen_hotkey, width=150)
        self.hotkey_btn.pack(side="right")
        self._show_hotkey()
        t.muted(
            frame,
            "Click, then press the key or combination (Esc cancels, Backspace turns it off). "
            "It only works while the game's window is in front, so other programs keep the key.",
            size=11, wraplength=480,
        ).pack(fill="x", padx=16, pady=(2, 6))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text="Capture sound", font=t.font(13), text_color=t.TEXT).pack(side="left")
        t.secondary_button(row, "▶", lambda: self.app.play_shutter(self._volume()), width=34,
                           height=28).pack(side="right", padx=(8, 0))
        self.volume_lbl = t.muted(row, "", width=40, anchor="e")
        self.volume_lbl.pack(side="right")
        self.volume = ctk.CTkSlider(
            row, from_=0, to=100, number_of_steps=20, width=170, command=lambda _v: self._show_volume(),
            fg_color=t.SURFACE_ALT, progress_color=t.ACCENT, button_color=t.ACCENT,
            button_hover_color=t.ACCENT_HOVER,
        )
        self.volume.set(int(self.cfg.get("screenshot_volume", 30)))
        self.volume.pack(side="right", padx=8)
        self._show_volume()
        t.muted(frame, "Folder", size=12).pack(fill="x", padx=16, pady=(6, 0))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 0))
        self.shot_dir = t.entry(row, placeholder_text=str(screenshots.default_root()))
        if (self.cfg.get("screenshot_dir") or "").strip():
            self.shot_dir.insert(0, self.cfg["screenshot_dir"])
        self.shot_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))
        t.secondary_button(row, "Browse…", self._browse_shot_dir, width=80).pack(side="left")
        t.muted(
            frame, "Each VN gets its own folder in there. Screenshots already taken aren't moved.",
            size=11, wraplength=480,
        ).pack(fill="x", padx=16, pady=(6, 4))

        _section(frame, "Japanese locale")
        t.muted(
            frame,
            "For VNs that show garbled text or won't start: pick “Launch with” on a game's page "
            "in the Library, and Play starts it through one of these.",
            size=11, wraplength=480,
        ).pack(fill="x", padx=16, pady=(0, 6))
        self.tool_paths = {
            which: self._path_row(frame, f"{launcher.LABELS[which]}  ({launcher.TOOL_EXE[which]})",
                                  self.cfg.get(launcher.TOOL_SETTING[which]) or "",
                                  lambda e, w=which: self._browse_tool(e, w))
            for which in (launcher.LOCALE_EMULATOR, launcher.NTLEA)
        }

        _section(frame, "App")
        self.start_minimized = t.switch(frame, "Start minimized to the tray", self.cfg["start_minimized"])
        self.launch_at_startup = t.switch(
            frame, "Launch when Windows starts", autostart.is_enabled(),
            hint="" if autostart.supported() else "Only available in the packaged .exe build.",
        )
        if not autostart.supported():
            self.launch_at_startup.configure(state="disabled")
        self.check_updates = t.switch(
            frame, "Check for updates at launch", self.cfg["check_updates"],
            hint=f"Version {__version__}. New GitHub releases are offered when the app starts."
            if updater.supported() else "Only available in the packaged .exe build.",
        )
        if not updater.supported():
            self.check_updates.configure(state="disabled")

        _section(frame, "Your data")
        t.muted(
            frame,
            "Settings, the Library (time read, history, statuses) and custom covers in one file, "
            "to move to another PC or keep a copy. It includes your VNDB token: don't share it.",
            size=11, wraplength=480,
        ).pack(fill="x", padx=16, pady=(0, 6))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        t.secondary_button(row, "Export…", self._export_data, width=110).pack(side="left")
        t.secondary_button(row, "Import…", self._import_data, width=110).pack(side="left", padx=(8, 0))

        _section(frame, "Advanced")
        self.min_interval = _field(frame, "Min. seconds between presence updates",
                                   str(self.cfg["update_min_interval"]), width=70)
        self.asset_key = _field(frame, "Fallback Discord asset key", str(self.cfg["default_asset_key"]),
                                width=150)
        ctk.CTkFrame(frame, fg_color="transparent", height=8).pack()

    def _show_hotkey(self, listening: bool = False) -> None:
        if listening:
            self.hotkey_btn.configure(text="Press a key…", border_color=t.ACCENT, text_color=t.ACCENT)
        else:
            self.hotkey_btn.configure(text=self._hotkey_value or "Off", border_color=t.BORDER,
                                      text_color=t.TEXT if self._hotkey_value else t.MUTED)

    def _volume(self) -> int:
        return int(round(self.volume.get()))

    def _show_volume(self) -> None:
        self.volume_lbl.configure(text=f"{self._volume()}%" if self._volume() else "Off")

    def _listen_hotkey(self) -> None:
        self._show_hotkey(listening=True)
        self._listening = True
        self.winfo_toplevel().focus_set()  # out of any text field, so the key isn't typed in it

    def on_key(self, event) -> str | None:
        """Every key pressed in the window while this page is shown (see App)."""
        return self._on_hotkey_key(event) if self._listening else None

    def _on_hotkey_key(self, event) -> str:
        pressed = event.type == tk.EventType.KeyPress
        if event.keysym == "Escape":
            if pressed:
                self._stop_listening()
        elif event.keysym in ("BackSpace", "Delete"):
            if pressed:
                self._hotkey_value = ""
                self._stop_listening()
        # Windows only reports Print Screen when it's released.
        elif pressed != (event.keysym == "Print"):
            combo = hotkey.from_key_event(event.keysym, event.state, event.keycode)
            if combo:  # None while only a modifier is down
                self._hotkey_value = combo
                self._stop_listening()
        return "break"

    def _stop_listening(self) -> None:
        self._listening = False
        self._show_hotkey()

    def _path_row(self, parent, label: str, value: str, browse) -> ctk.CTkEntry:
        t.muted(parent, label, size=12).pack(fill="x", padx=16, pady=(4, 0))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 4))
        ent = t.entry(row, placeholder_text="Not set")
        if value:  # inserting even "" would hide the placeholder
            ent.insert(0, value)
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        t.secondary_button(row, "Browse…", lambda: browse(ent), width=80).pack(side="left")
        return ent

    def _browse_tool(self, ent: ctk.CTkEntry, which: str) -> None:
        exe = launcher.TOOL_EXE[which]
        current = ent.get().strip()
        path = filedialog.askopenfilename(
            parent=self, title=f"Locate {exe}", filetypes=[(exe, exe), ("Programs", "*.exe")],
            initialdir=os.path.dirname(current) if os.path.isdir(os.path.dirname(current)) else None,
        )
        if path:
            ent.delete(0, tk.END)
            ent.insert(0, os.path.normpath(path))

    def _browse_shot_dir(self) -> None:
        start = self.shot_dir.get().strip() or str(screenshots.root(self.cfg))
        path = filedialog.askdirectory(parent=self, title="Screenshot folder",
                                       initialdir=start if os.path.isdir(start) else None)
        if path:
            self.shot_dir.delete(0, tk.END)
            self.shot_dir.insert(0, os.path.normpath(path))

    def _test_connection(self) -> None:
        if not self.test_lbl.winfo_manager():
            self.test_lbl.pack(fill="x", padx=16, pady=(4, 0), before=self._hint_anchor)
        cid = self.client_id.get().strip()
        if not cid.isdigit():
            self.test_lbl.configure(text="An Application ID is a long number.", text_color=t.RED)
            return
        self.test_lbl.configure(text="Testing…", text_color=t.MUTED)

        def worker() -> None:
            ok, msg = True, "Connected — this ID works."
            try:
                from pypresence import Presence

                rpc = Presence(cid)
                rpc.connect()
                rpc.close()
            except Exception as exc:
                ok, msg = False, f"Failed: {type(exc).__name__} (is Discord running?)"

            def show() -> None:
                if self.winfo_exists():
                    self.test_lbl.configure(text=msg, text_color=t.GREEN if ok else t.RED)
            try:
                self.after(0, show)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _test_vndb_token(self) -> None:
        if not self.vndb_test_lbl.winfo_manager():
            self.vndb_test_lbl.pack(fill="x", padx=16, pady=(4, 0), before=self._vndb_hint)
        token = self.vndb_token.get().strip()
        if not token:
            self.vndb_test_lbl.configure(text="Paste a token first.", text_color=t.RED)
            return
        self.vndb_test_lbl.configure(text="Testing…", text_color=t.MUTED)

        def worker() -> None:
            try:
                ok, msg = True, f"Connected as {self.engine.check_vndb_token(token)}."
            except Exception as exc:
                ok, msg = False, f"Failed: {exc}"

            def show() -> None:
                if self.winfo_exists():
                    self.vndb_test_lbl.configure(text=msg, text_color=t.GREEN if ok else t.RED)
            try:
                self.after(0, show)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _build_rules(self, frame) -> None:
        t.muted(
            frame,
            "Extra rules run before the built-in ones. One JSON object per line; "
            "the first rule whose pattern matches the window title wins.",
            size=12, wraplength=500,
        ).pack(fill="x", padx=12, pady=(10, 4))
        example = ctk.CTkLabel(
            frame, text='{"name": "part", "pattern": "part\\\\s*(?P<n>\\\\d+)", "label": "Part {n}", '
                        '"section_type": "chapter"}',
            font=t.mono(11), text_color=t.MUTED, fg_color=t.SURFACE_ALT, corner_radius=6,
            anchor="w", justify="left", wraplength=500,
        )
        example.pack(fill="x", padx=12, pady=(0, 8), ipadx=8, ipady=6)
        self.rules_text = ctk.CTkTextbox(
            frame, font=t.mono(12), fg_color=t.SURFACE_ALT, border_color=t.BORDER, border_width=1,
            corner_radius=8, text_color=t.TEXT, wrap="none",
        )
        self.rules_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        existing = self.cfg.get("title_rules") or []
        self.rules_text.insert("1.0", "\n".join(json.dumps(r, ensure_ascii=False) for r in existing))

    def _build_blacklist(self, frame) -> None:
        t.muted(
            frame,
            "Programs that are never detected as a visual novel, one per line "
            "(e.g. osu!.exe). Their games are also hidden from the Library. "
            "Browsers, Discord, Steam, OBS… are always ignored.",
            size=12, wraplength=500,
        ).pack(fill="x", padx=12, pady=(10, 8))
        self.blacklist_text = ctk.CTkTextbox(
            frame, font=t.mono(12), fg_color=t.SURFACE_ALT, border_color=t.BORDER, border_width=1,
            corner_radius=8, text_color=t.TEXT, wrap="none",
        )
        self.blacklist_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.blacklist_text.insert("1.0", "\n".join(str(e) for e in self.cfg.get("blacklist_exe") or []))

    def _parse_blacklist(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for line in self.blacklist_text.get("1.0", tk.END).splitlines():
            name = os.path.basename(line.strip())
            if not name:
                continue
            if not name.lower().endswith(".exe"):
                name += ".exe"
            if normalize_exe(name) not in seen:
                seen.add(normalize_exe(name))
                out.append(name)
        return out

    def _parse_rules(self) -> list[dict]:
        """Raise ValueError with a line number on anything the engine would reject."""
        out = []
        for n, line in enumerate(self.rules_text.get("1.0", tk.END).splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rule = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Line {n}: invalid JSON ({exc.msg}).") from None
            if not isinstance(rule, dict) or not isinstance(rule.get("pattern"), str):
                raise ValueError(f'Line {n}: each rule must be an object with a "pattern" string.')
            try:
                re.compile(rule["pattern"])
            except re.error as exc:
                raise ValueError(f"Line {n}: invalid regex ({exc}).") from None
            out.append(rule)
        return out

    def _export_data(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Export data", defaultextension=".zip",
            initialfile=backup.default_name(), filetypes=[("Visual Novel RPC backup", "*.zip")],
        )
        if not path:
            return
        try:
            count = backup.export_data(self.cfg, Path(path))
        except OSError as exc:
            messagebox.showerror("Export data", f"Couldn't write the file: {exc}", parent=self)
            return
        messagebox.showinfo("Export data", f"Saved {count} VN{'s' * (count != 1)} and your settings to\n{path}",
                            parent=self)

    def _import_data(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Import data", filetypes=[("Visual Novel RPC backup", "*.zip")],
        )
        if not path or not messagebox.askyesno(
            "Import data",
            "Replace your settings and Library with the ones in this file?\n\n"
            f"What you have now is saved first in\n{backup.BACKUP_DIR}",
            parent=self, icon="warning",
        ):
            return
        try:
            count = backup.import_data(self.cfg, Path(path))
        except (backup.BackupError, OSError) as exc:
            messagebox.showerror("Import data", f"Couldn't import it: {exc}", parent=self)
            return
        self.engine.reload_config()
        self.app.apply_screenshot_settings()
        messagebox.showinfo("Import data", f"Loaded {count} VN{'s' * (count != 1)} and the settings.",
                            parent=self)
        app = self.app
        app.after(50, app.rebuild_ui)  # new theme, and every page shows the imported data

    def _save(self) -> None:
        try:
            rules = self._parse_rules()
        except ValueError as exc:
            messagebox.showerror("Title rules", str(exc), parent=self)
            return
        try:
            custom = self.theme_tab.custom_value()
        except ValueError as exc:
            messagebox.showerror("Custom theme", str(exc), parent=self)
            return
        try:
            interval = max(1, int(float(self.min_interval.get())))
        except ValueError:
            interval = DEFAULTS["update_min_interval"]
        try:
            idle_seconds = max(0, int(float(self.idle_seconds.get())))
        except ValueError:
            idle_seconds = DEFAULTS["idle_seconds"]

        self.cfg["discord_client_id"] = self.client_id.get().strip() or self.cfg["discord_client_id"]
        self.cfg["show_elapsed"] = bool(self.show_elapsed.get())
        self.cfg["show_section"] = bool(self.show_section.get())
        self.cfg["show_total_read"] = bool(self.show_total_read.get())
        self.cfg["clear_on_close"] = bool(self.clear_on_close.get())
        self.cfg["show_vndb_button"] = bool(self.show_vndb_button.get())
        self.cfg["idle_when_unfocused"] = bool(self.idle_when_unfocused.get())
        self.cfg["idle_seconds"] = idle_seconds
        self.cfg["allow_nsfw_covers"] = bool(self.allow_nsfw.get())
        self.cfg["use_steam_names"] = bool(self.use_steam_names.get())
        self.cfg["vndb_token"] = self.vndb_token.get().strip()
        self.cfg["vndb_sync"] = bool(self.vndb_sync.get())
        self.cfg["start_minimized"] = bool(self.start_minimized.get())
        self.cfg["check_updates"] = bool(self.check_updates.get())
        self.cfg["update_min_interval"] = interval
        self.cfg["default_asset_key"] = self.asset_key.get().strip() or DEFAULTS["default_asset_key"]
        self.cfg["title_rules"] = rules
        self.cfg["blacklist_exe"] = self._parse_blacklist()
        self.cfg["screenshot_hotkey"] = self._hotkey_value
        self.cfg["screenshot_dir"] = self.shot_dir.get().strip()
        self.cfg["screenshot_volume"] = self._volume()
        for which, ent in self.tool_paths.items():
            self.cfg[launcher.TOOL_SETTING[which]] = ent.get().strip()
        if autostart.supported():
            try:
                autostart.set_enabled(bool(self.launch_at_startup.get()))
            except OSError as exc:
                messagebox.showwarning("Startup", f"Couldn't change the startup setting: {exc}", parent=self)
        new_theme = self.theme_tab.theme_name()
        old_custom = self.cfg.get("custom_theme")
        self.cfg["theme"] = new_theme
        self.cfg["custom_theme"] = custom
        self.cfg.save()
        self.engine.reload_config()
        self.app.apply_screenshot_settings()
        restyle = new_theme != t.current_theme or (new_theme == "custom" and custom != old_custom)
        if restyle:
            # Re-theming rebuilds every widget, this page included: come back to the same tab.
            app = self.app
            app.after(50, app.rebuild_ui)
            return
        self.save_btn.configure(text="Saved ✓")
        self.after(1500, lambda: self.save_btn.winfo_exists() and self.save_btn.configure(text="Save"))


def _section(parent, title: str) -> None:
    t.overline(parent, title, color=t.ACCENT).pack(fill="x", padx=16, pady=(16, 6))


def _field(parent, label: str, value: str, *, width: int) -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=4)
    ctk.CTkLabel(row, text=label, font=t.font(13), text_color=t.TEXT).pack(side="left")
    ent = t.entry(row, width=width)
    ent.insert(0, value)
    ent.pack(side="right")
    return ent
