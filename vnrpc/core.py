from __future__ import annotations

import difflib
import re
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import screenshots, steam
from .config import STATUSES, Config
from .covers import Cover, cover_from_vn, resolve_cover
from .engines import blacklist_set, clean_title, normalize_exe
from .presence import Activity, PresenceManager
from .title_parser import Rule, build_rules, parse, strip_game_name
from .vndb import ReleaseCover, VNDBClient, VNDBError, VNResult, push_list_status
from .winapi import CaptureError, capture_window, foreground_window, window_pid
from .window_watcher import TargetState, WindowWatcher

_SECTION_TAIL = re.compile(r"\s*[-–—~～:|].*$")

_PLAYTIME_FLUSH_INTERVAL = 60.0
_IDLE_POLL = 1.0


def format_playtime(seconds: int) -> str:
    """``5102`` -> ``"1h 25m"``."""
    total_minutes = max(0, int(seconds)) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


@dataclass
class Snapshot:
    """Everything the UI needs to draw the "now playing" card."""
    detected: bool = False
    key: str = ""
    exe: str = ""
    engine_name: str = ""
    raw_title: str = ""
    game_name: str = ""
    section_type: str = ""
    section_label: str = ""
    cover: Cover = field(default_factory=Cover)
    vn: VNResult | None = None
    vndb_locked: bool = False
    presence_text: str = ""
    steam_name: str = ""
    privacy: str = "full"
    playtime_seconds: int = 0
    playtime_text: str = ""
    session_start: int = 0
    hwnd: int = 0
    pid: int = 0
    idle: bool = False  # the VN has been in the background for a while: nothing shared, timers stopped


class VNRPCEngine:
    def __init__(
        self,
        config: Config,
        *,
        on_snapshot: Callable[[Snapshot], None] | None = None,
        on_status: Callable[[str, bool, str], None] | None = None,
    ) -> None:
        self.config = config
        self._on_snapshot = on_snapshot or (lambda snap: None)
        self._on_status = on_status or (lambda kind, ok, msg: None)

        self.vndb = VNDBClient()
        self.presence = PresenceManager(
            config["discord_client_id"],
            min_interval=config["update_min_interval"],
            on_status=lambda ok, msg: self._on_status("discord", ok, msg),
        )
        self.watcher = WindowWatcher(self._handle_target)

        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        self._current_key = ""
        self._session_start = 0
        self._auto_match: dict[str, VNResult | None] = {}
        self._syncing: set[str] = set()
        self._rules: list[Rule] = build_rules(config.get("title_rules"))
        self._paused = False

        self._playtime_key = ""
        self._playtime_tick_start = 0.0
        self._playtime_lock = threading.Lock()
        self._playtime_thread: threading.Thread | None = None
        self._playtime_stop = threading.Event()
        self._idle_thread: threading.Thread | None = None

        # Idle mode (all under _playtime_lock): when the VN's window lost the focus,
        # and whether it's been away long enough to count as idle.
        self._unfocused_since = 0.0
        self._idle_since = 0.0
        self._idle = False

    def start(self) -> None:
        self._apply_watcher_config()
        self.presence.start()
        self.watcher.start()
        self._playtime_stop.clear()
        self._playtime_thread = threading.Thread(target=self._playtime_loop, name="playtime", daemon=True)
        self._playtime_thread.start()
        self._idle_thread = threading.Thread(target=self._idle_loop, name="idle", daemon=True)
        self._idle_thread.start()

    def stop(self) -> None:
        self._playtime_stop.set()
        for thread in (self._playtime_thread, self._idle_thread):
            if thread:
                thread.join(timeout=2)
        self._flush_playtime()
        self.watcher.stop()
        self.presence.stop()

    def set_paused(self, paused: bool) -> None:
        with self._playtime_lock:
            if paused:
                self._flush_playtime_locked()
            else:
                self._playtime_tick_start = time.time()
            self._paused = paused
        self.presence.set_paused(paused)
        if not paused:
            self.watcher.poke()

    def reload_config(self) -> None:
        self._rules = build_rules(self.config.get("title_rules"))
        self.presence.set_client_id(self.config["discord_client_id"])
        self.presence.set_min_interval(self.config["update_min_interval"])
        self._apply_watcher_config()
        self.watcher.poke()
        self._auto_match.clear()

    def _apply_watcher_config(self) -> None:
        mt = self.config["manual_target"]
        self.watcher.configure(
            mode=self.config["detection_mode"],
            manual_exe=mt.get("exe", ""),
            manual_title_contains=mt.get("title_contains", ""),
            blacklist=self.blacklist,
        )
        self.watcher.set_known_paths(self.config.known_game_paths())

    @property
    def blacklist(self) -> frozenset[str]:
        """Built-in + user-blacklisted exe names, normalized (``"medal.exe"``)."""
        return blacklist_set(self.config.get("blacklist_exe"))

    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def list_windows(self):
        return self.watcher.list_windows()

    def _handle_target(self, target: TargetState | None) -> None:
        if target is None:
            # Clear Discord first: saving the playtime below touches the disk and can fail.
            if self.config["clear_on_close"]:
                self.presence.set_activity(None)
            self._current_key = ""
            self._store(Snapshot(detected=False))
            self._on_status("game", False, "no visual novel detected")
            with self._playtime_lock:
                self._flush_playtime_locked()
                self._playtime_key = ""
                self._reset_idle_locked()
            return

        key = self.config.key_for(target.exe, target.exe_path)
        if key != self._current_key:
            with self._playtime_lock:
                self._flush_playtime_locked()
                self._playtime_key = key
                self._playtime_tick_start = time.time()
                self._reset_idle_locked()
            self._current_key = key
            self._session_start = int(time.time())
            self.config.start_session(key)

        override = self.config.game_override(key)
        if target.exe_path and override.get("path") != target.exe_path:
            self.config.set_game_override(key, path=target.exe_path)
            override = self.config.game_override(key)
            self.watcher.set_known_paths(self.config.known_game_paths())
        cleaned = clean_title(target.raw_title, None) if not target.engine_name else clean_title(
            target.raw_title, _engine_by_name(target.engine_name)
        )

        steam_name = ""
        if self.config.get("use_steam_names", True):
            try:
                app = steam.app_for_exe(target.exe_path)
                steam_name = app.name if app else ""
            except Exception:
                steam_name = ""

        vn = self._resolve_vn(key, cleaned, override, steam_name)
        game_name = (
            override.get("title")
            or (vn.title if vn else "")
            or steam_name
            or _guess_game_name(cleaned)
        )
        # Remember what was detected so the Library can show a name and cover instead of the exe.
        learned = {}
        if game_name and not override.get("title") and override.get("name") != game_name:
            learned["name"] = game_name
        if vn and not override.get("vndb_id") and override.get("matched_vndb_id") != vn.id:
            learned["matched_vndb_id"] = vn.id
        if "status" not in override:  # "" means the user cleared it: leave it be
            learned["status"] = "playing"
        if learned:
            self.config.set_game_override(key, **learned)
        vn_id = override.get("vndb_id")
        if vn_id and override.get("vndb_synced") != vn_id:
            # First time this VN is read with list sync on: mark it Playing on VNDB,
            # unless it's already on the list with a status of its own.
            self._sync_list_status(key, vn_id, override.get("status") or "playing", keep_existing=True)

        rules = build_rules((override.get("title_rules") or []) + (self.config.get("title_rules") or []))
        info = parse(cleaned, game_name, rules)

        cover = self._resolve_cover(override, vn, game_name)
        if cover.source != "none" and override.get("cover_nsfw") != cover.nsfw:
            # Remembered so the stats card never shares a flagged cover by accident.
            self.config.set_game_override(key, cover_nsfw=cover.nsfw)
        privacy = (override.get("privacy") or "full").lower()
        playtime_seconds = self.config.get_playtime_seconds(key)

        snap = Snapshot(
            detected=True,
            key=key,
            exe=target.exe,
            engine_name=target.engine_name,
            raw_title=target.raw_title,
            game_name=game_name,
            section_type=info.section_type,
            section_label=info.section_label,
            cover=cover,
            vn=vn,
            vndb_locked=bool(override.get("vndb_id") or override.get("cover_source")),
            steam_name=steam_name,
            privacy=privacy,
            playtime_seconds=playtime_seconds,
            playtime_text=format_playtime(playtime_seconds),
            session_start=self._session_start,
            hwnd=target.hwnd,
            pid=target.pid,
            idle=self._idle,
        )
        snap.presence_text = _preview(game_name, info.section_label)
        self._store(snap)
        self._on_status("game", True, f"{game_name or target.exe}")
        self._push_presence(snap)

    def _resolve_vn(self, key: str, cleaned: str, override: dict, steam_name: str = "") -> VNResult | None:
        if override.get("vndb_id"):
            cache_key = "id:" + override["vndb_id"]
            if cache_key in self._auto_match:
                return self._auto_match[cache_key]
            try:
                vn = self.vndb.get_vn(override["vndb_id"])
            except Exception as exc:
                vn = None
                self._on_status("vndb", False, f"VNDB lookup failed: {exc}")
            self._auto_match[cache_key] = vn
            return vn
        if override.get("cover_source") in ("url", "local", "none"):
            return None
        if key in self._auto_match:
            return self._auto_match[key]
        query = steam_name or _search_query(cleaned)
        vn = None
        try:
            results = self.vndb.search_vn(query, limit=8)
            vn = _best_vn_match(results, query)
        except Exception as exc:
            self._on_status("vndb", False, f"VNDB lookup failed: {exc}")
        self._auto_match[key] = vn
        return vn

    def _resolve_cover(self, override: dict, vn: VNResult | None, game_name: str) -> Cover:
        allow_nsfw = self.config["allow_nsfw_covers"]
        asset = self.config["default_asset_key"]
        source = override.get("cover_source")
        if source:
            try:
                return resolve_cover(
                    source,
                    override.get("cover_value", ""),
                    vndb=self.vndb,
                    allow_nsfw=allow_nsfw,
                    default_asset_key=asset,
                    label=game_name,
                    vn=vn,
                )
            except Exception as exc:
                self._on_status("vndb", False, f"cover lookup failed: {exc}")
                if vn is None:
                    return Cover(source="none")
        if vn is not None:
            cover = cover_from_vn(vn, allow_nsfw=allow_nsfw, default_asset_key=asset)
            # Cache it on disk so the Library has a thumbnail for auto-matched VNs too.
            cover.local_path = self.vndb.cover_path(vn.id, vn.image_url)
            return cover
        return Cover(source="none")

    def _resolve_cover_for_vn_id(self, vn_id: str, game_name: str) -> Cover:
        return resolve_cover(
            "vndb", vn_id, vndb=self.vndb,
            allow_nsfw=self.config["allow_nsfw_covers"],
            default_asset_key=self.config["default_asset_key"],
            label=game_name,
        )

    def activity_for(self, snap: Snapshot) -> Activity | None:
        """Exactly what gets pushed to Discord for ``snap`` (``None`` = nothing).
        The UI's preview renders this too, so the two can't drift apart."""
        if not snap.detected or snap.privacy == "off" or snap.idle:
            return None
        start = (snap.session_start or None) if self.config["show_elapsed"] else None
        if snap.privacy == "private":
            return Activity(
                name="Visual Novel",
                details="Reading",
                large_image=self.config["default_asset_key"],
                large_text="Visual Novel",
                small_text="via Visual Novel RPC",
                start=start,
                buttons=[],
            )
        buttons = []
        if self.config["show_vndb_button"] and snap.vn is not None and snap.privacy != "partial":
            buttons.append({"label": "View on VNDB", "url": snap.vn.vndb_url})
        show_total = self.config.get("show_total_read", True)
        state = f"Total read: {snap.playtime_text}" if show_total and snap.playtime_seconds > 0 else ""
        show_section = self.config.get("show_section", True) and snap.privacy != "partial"
        return Activity(
            name=snap.game_name or snap.raw_title or "Visual Novel",
            details=_reading_line(snap.section_label) if show_section else "",
            state=state,
            large_image=snap.cover.discord_image or self.config["default_asset_key"],
            large_text=snap.cover.label or snap.game_name,
            small_text="via Visual Novel RPC",
            start=start,
            buttons=buttons,
        )

    def _push_presence(self, snap: Snapshot) -> None:
        if self._paused:
            return
        self.presence.set_activity(self.activity_for(snap))

    def _store(self, snap: Snapshot) -> None:
        with self._lock:
            self._snapshot = snap
        self._on_snapshot(snap)

    def _flush_playtime(self) -> None:
        """Bank whatever time has passed since the last flush for the active game."""
        with self._playtime_lock:
            self._flush_playtime_locked()

    def _flush_playtime_locked(self) -> None:
        if self._paused or self._idle or not self._playtime_key or self._playtime_tick_start <= 0:
            return
        # While the VN is in the background, only count up to when it lost the focus:
        # if it turns out to be idle, that time was never reading.
        end = min(time.time(), self._unfocused_since or float("inf"))
        elapsed = end - self._playtime_tick_start
        if elapsed > 0:
            self._playtime_tick_start = end
            try:
                self.config.add_playtime_seconds(self._playtime_key, elapsed)
            except OSError as exc:  # e.g. the game's file is locked by an antivirus or sync tool
                self._on_status("game", False, f"couldn't save playtime: {exc}")

    def _playtime_loop(self) -> None:
        """Periodically save elapsed time and refresh the "total hours read" figure
        so it climbs live in the UI and on Discord while a VN stays in focus."""
        while not self._playtime_stop.wait(_PLAYTIME_FLUSH_INTERVAL):
            if self._paused or not self._playtime_key:
                continue
            with self._lock:
                snap = self._snapshot
            if not snap.detected:
                continue
            self._flush_playtime()
            total = self.config.get_playtime_seconds(snap.key)
            new_snap = replace(snap, playtime_seconds=total, playtime_text=format_playtime(total))
            with self._lock:
                if self._snapshot is not snap:
                    continue
                self._snapshot = new_snap
            self._on_snapshot(new_snap)
            self._push_presence(new_snap)

    def _idle_loop(self) -> None:
        while not self._playtime_stop.wait(_IDLE_POLL):
            try:
                self._check_idle()
            except Exception:
                pass

    def _check_idle(self, now: float | None = None) -> None:
        """Idle mode: once the VN's window has stayed in the background for
        ``idle_seconds``, Discord is cleared and the elapsed and playtime counters
        stop; they carry on from where they were when it comes back to the front."""
        now = time.time() if now is None else now
        snap = self.snapshot
        enabled = bool(self.config.get("idle_when_unfocused"))
        focused = not (enabled and snap.detected) or _has_focus(snap)
        with self._playtime_lock:
            if focused:
                self._unfocused_since = 0.0
                if not self._idle:
                    return
                self._session_start += max(0, int(now - self._idle_since))
                self._playtime_tick_start = now
                self._idle = False
            elif not self._unfocused_since:
                self._unfocused_since = now
                return
            elif self._idle or now - self._unfocused_since < max(0, float(self.config.get("idle_seconds") or 0)):
                return
            else:
                self._flush_playtime_locked()  # up to when the focus was lost
                self._idle = True
                self._idle_since = self._unfocused_since
            idle, start = self._idle, self._session_start
        with self._lock:
            if not self._snapshot.detected:
                return
            snap = self._snapshot = replace(self._snapshot, idle=idle, session_start=start)
        self._on_snapshot(snap)
        self._push_presence(snap)

    def _reset_idle_locked(self) -> None:
        """Another game (or none): its idle state doesn't carry over."""
        self._unfocused_since = 0.0
        self._idle = False

    @property
    def idle(self) -> bool:
        return self._idle

    def apply_vn_choice(self, key: str, vn: VNResult, *, as_cover: bool = True) -> None:
        """User picked a VN in the cover dialog's VNDB tab."""
        fields = {"vndb_id": vn.id, "title": vn.title}
        if as_cover:
            fields.update(cover_source="vndb", cover_value=vn.id)
        self.config.set_game_override(key, **fields)
        self.reload_config()

    def apply_release_cover(self, key: str, vn: VNResult, image_url: str) -> None:
        """User picked a specific release's box art in the cover dialog."""
        self.config.set_game_override(
            key, vndb_id=vn.id, title=vn.title, cover_source="url", cover_value=image_url
        )
        self.reload_config()

    def get_release_covers(self, vn_id: str) -> list[ReleaseCover]:
        return self.vndb.get_release_covers(vn_id)

    def apply_cover_url(self, key: str, url: str) -> None:
        self.config.set_game_override(key, cover_source="url", cover_value=url)
        self.reload_config()

    def apply_cover_local(self, key: str, path: str) -> None:
        self.config.set_game_override(key, cover_source="local", cover_value=path)
        self.reload_config()

    def set_game_privacy(self, key: str, mode: str) -> None:
        self.config.set_game_override(key, privacy=mode)
        self.reload_config()

    def set_game_path(self, key: str, path: str) -> None:
        """User located a Library VN's exe by hand (it was never saved, or moved)."""
        self.config.set_game_override(key, path=path)
        self.reload_config()

    def add_to_blacklist(self, exe: str) -> None:
        """Never detect ``exe`` again (the main window's "Not a VN" button)."""
        entries = list(self.config.get("blacklist_exe") or [])
        if normalize_exe(exe) not in {normalize_exe(e) for e in entries}:
            entries.append(exe)
            self.config["blacklist_exe"] = entries
            self.config.save()
        self.reload_config()

    def clear_override(self, key: str) -> None:
        self.config.clear_game_override(key)
        self.reload_config()

    def reset_playtime(self, key: str) -> None:
        with self._playtime_lock:
            self.config.reset_playtime(key)
            if key == self._playtime_key:
                self._playtime_tick_start = time.time()
        self.reload_config()

    def confirm_vn_match(self, key: str) -> None:
        """Library: keep the automatic VNDB match for good (this is what list sync uses)."""
        entry = self.config.game_override(key)
        vn_id = entry.get("matched_vndb_id")
        if vn_id:
            self.config.set_game_override(key, vndb_id=vn_id, title=entry.get("name") or None)
            self.reload_config()

    def set_game_status(self, key: str, status: str) -> None:
        """Library: the user set Playing / Finished / Stalled / Dropped by hand, or
        cleared it (``""``)."""
        if status not in STATUSES and status != "":
            return
        self.config.set_game_override(key, status=status)
        vn_id = self.config.game_override(key).get("vndb_id")
        if vn_id:
            self._sync_list_status(key, vn_id, status, keep_existing=False)

    def _sync_list_status(self, key: str, vn_id: str, status: str, *, keep_existing: bool) -> None:
        """Push ``status`` to the user's VNDB list in the background (when enabled)."""
        token = (self.config.get("vndb_token") or "").strip()
        if not (self.config.get("vndb_sync") and token) or vn_id in self._syncing:
            return
        self._syncing.add(vn_id)

        def worker() -> None:
            try:
                now = push_list_status(self.vndb, token, vn_id, status, keep_existing=keep_existing)
            except Exception as exc:
                self._on_status("vndb", False, f"VNDB list sync failed: {exc}")
                return
            finally:
                self._syncing.discard(vn_id)
            fields = {"vndb_synced": vn_id}
            if now != status:
                fields["status"] = now  # it was already on the list with another status
            self.config.set_game_override(key, **fields)
            self._on_status("vndb", True, f"VNDB list: {vn_id} → {now.capitalize() or 'no status'}")

        threading.Thread(target=worker, name="vndb-sync", daemon=True).start()

    def _rating_target(self, key: str) -> tuple[str, str]:
        token = (self.config.get("vndb_token") or "").strip()
        vn_id = self.config.game_override(key).get("vndb_id")
        if not token:
            raise VNDBError("add your VNDB token in Settings first")
        if not vn_id:
            raise VNDBError("confirm this VN's VNDB entry first")
        return token, vn_id

    def vndb_vote(self, key: str) -> int | None:
        """The user's rating of this VN on VNDB (10-100), or None. Blocking; raises VNDBError."""
        token, vn_id = self._rating_target(key)
        vote = (self.vndb.get_list_entry(token, vn_id) or {}).get("vote") or None
        self.config.set_game_override(key, vndb_vote=vote or 0)  # shown before VNDB answers next time
        return vote

    def set_vndb_vote(self, key: str, vote: int | None) -> None:
        """Rate this VN on VNDB (10-100), or remove the rating with None. Blocking;
        raises VNDBError. VNDB adds the VN to the list if it wasn't there."""
        token, vn_id = self._rating_target(key)
        if vote is not None and not 10 <= vote <= 100:
            raise ValueError(f"a VNDB rating is 10-100, not {vote}")
        self.vndb.update_list_entry(token, vn_id, {"vote": vote})
        self.config.set_game_override(key, vndb_vote=vote or 0)

    def take_screenshot(self, on_captured: Callable[[], None] | None = None) -> Path:
        """Capture the running VN's window into its screenshot folder. Raises
        CaptureError (or OSError when it can't be saved). ``on_captured`` runs as
        soon as the image is taken, before the (slower) saving."""
        snap = self.snapshot
        if not snap.detected or not snap.hwnd:
            raise CaptureError("No visual novel is running.")
        img = capture_window(snap.hwnd)
        if on_captured:
            on_captured()
        folder = screenshots.folder_for(self.config, snap.key, create=True)
        return screenshots.save(img, folder, game=snap.game_name, section=snap.section_label)

    def check_vndb_token(self, token: str) -> str:
        """Settings' Test button: the token's username, or a VNDBError saying what's wrong."""
        return self.vndb.list_user(token.strip())["username"]

    def search_vndb(self, query: str, limit: int = 12) -> list[VNResult]:
        return self.vndb.search_vn(query, limit=limit)


def _has_focus(snap: Snapshot) -> bool:
    """The VN's window, or another of its process's (a settings dialog, a
    backlog window…), is the one in front."""
    fg = foreground_window()
    return bool(fg) and (fg == snap.hwnd or (snap.pid and window_pid(fg) == snap.pid))


def _engine_by_name(name: str):
    from .engines import ENGINES
    for eng in ENGINES:
        if eng.name == name:
            return eng
    return None


def _guess_game_name(cleaned: str) -> str:
    head = _SECTION_TAIL.sub("", cleaned).strip(" -–—|:·•")
    return head or cleaned.strip()


def _search_query(cleaned: str) -> str:
    q = _SECTION_TAIL.sub("", cleaned)
    q = re.sub(r"\bver(?:sion)?\.?\s*[\d.;]+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\bv?\d+[.;]\d+(?:[.;]\d+)*[a-z]?\b", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"[\[\]（）()【】]", " ", q)
    return re.sub(r"\s{2,}", " ", q).strip() or cleaned.strip()


def _preview(game: str, section: str) -> str:
    if game and section:
        return f"{game}  —  {section}"
    return game or section or ""


def _reading_line(section_label: str) -> str:
    return f"Reading — {section_label}" if section_label else "Reading"


_NAME_MATCH_THRESHOLD = 0.6


def _best_vn_match(results: list[VNResult], query: str) -> VNResult | None:
    """Prefer the candidate whose title best matches the query; if nothing is a
    confident name match, fall back to the highest-rated candidate instead of
    blindly trusting VNDB's own top search result."""
    if not results:
        return None
    q = _loose(query)
    if not q:
        return results[0]
    best_vn, best_score = results[0], 0.0
    for vn in results:
        score = max(_similarity(q, _loose(vn.title)), _similarity(q, _loose(vn.alt_title)))
        if score > best_score:
            best_vn, best_score = vn, score
    if best_score >= _NAME_MATCH_THRESHOLD:
        return best_vn
    return max(results, key=lambda vn: vn.rating or 0.0)


def _loose(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "")).lower()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _main() -> None:  # pragma: no cover
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = Config.load()

    def on_snap(s: Snapshot) -> None:
        if s.detected:
            logging.info("PRESENCE  %s | cover=%s(%s)", s.presence_text, s.cover.source, s.cover.discord_image[:60])
        else:
            logging.info("PRESENCE  (cleared)")

    def on_status(kind: str, ok: bool, msg: str) -> None:
        logging.info("[%s] %s%s", kind, "OK " if ok else "-- ", msg)

    engine = VNRPCEngine(cfg, on_snapshot=on_snap, on_status=on_status)
    engine.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()


if __name__ == "__main__":  # pragma: no cover
    _main()
