from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from .paths import CONFIG_FILE, GAMES_DIR, SETTINGS_FILE, ensure_dirs

DEFAULT_CLIENT_ID = "1466261523889393892"

DEFAULTS: dict[str, Any] = {
    "discord_client_id": DEFAULT_CLIENT_ID,
    "detection_mode": "auto",
    "manual_target": {
        "exe": "",
        "title_contains": "",
    },
    "allow_nsfw_covers": False,
    "use_steam_names": True,
    "show_elapsed": True,
    "show_section": True,
    "show_total_read": True,
    "clear_on_close": True,
    "idle_minutes": 0,
    "update_min_interval": 5,
    "start_minimized": False,
    "check_updates": True,
    "theme": "system",
    "custom_theme": {
        "mode": "dark", "BG": "#111214", "SURFACE": "#1B1C20", "ACCENT": "#5865F2", "TEXT": "#F2F3F5",
        "overrides": {},
    },
    "default_asset_key": "vn_cover",
    "show_vndb_button": True,
    "title_rules": [],
    "blacklist_exe": ["osu!.exe", "Medal.exe", "Riot Client.exe"],
    "vndb_token": "",
    "vndb_sync": False,
    "screenshot_hotkey": "PrintScreen",
    "screenshot_volume": 30,  # %, 0 = silent
    "screenshot_dir": "",  # "" = Pictures\Visual Novel RPC
    "locale_emulator_path": "",  # LEProc.exe
    "ntlea_path": "",  # ntleas.exe
}

STATUSES = ("playing", "finished", "stalled", "dropped")

_LEGACY_GAME_FIELDS = {"custom_name": "title", "exe_path": "path"}


def game_key(exe: str) -> str:
    """Normalize an exe name into a stable per-game key (and games/<key>.yaml stem)."""
    name = os.path.basename(exe or "").strip().lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def _norm_path(path: Any) -> str:
    return os.path.normcase(os.path.normpath(path)) if isinstance(path, str) and path else ""


def _folder_name(path: str) -> str:
    return os.path.basename(os.path.dirname(path or "")).strip().lower()


def _day(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _safe_filename(key: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in key)
    return cleaned or "game"


def _merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in DEFAULTS.items()}
    for key, value in (data or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key].update(value)
        else:
            out[key] = value
    return out


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Config:
    def __init__(
        self,
        data: dict[str, Any] | None = None,
        games: dict[str, dict[str, Any]] | None = None,
        game_filenames: dict[str, str] | None = None,
    ) -> None:
        self._data = _merge_defaults(data or {})
        self._games: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (games or {}).items()}
        self._game_filenames: dict[str, str] = dict(game_filenames or {})
        self._lock = threading.RLock()
        self._playtime_frac: dict[str, float] = {}

    @classmethod
    def load(cls) -> "Config":
        ensure_dirs()
        if not CONFIG_FILE.exists() and SETTINGS_FILE.exists():
            return cls._migrate_from_legacy()

        data: dict[str, Any] = {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (FileNotFoundError, yaml.YAMLError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}

        games: dict[str, dict[str, Any]] = {}
        game_filenames: dict[str, str] = {}
        for path in sorted(GAMES_DIR.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    entry = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(entry, dict):
                continue
            key = entry.pop("_key", None) or path.stem
            games[key] = entry
            game_filenames[key] = path.stem

        cfg = cls(data, games, game_filenames)
        if not CONFIG_FILE.exists():
            cfg.save()
        for key, entry in list(cfg._games.items()):
            if cfg._game_filenames.get(key) != cfg._filename_for(key, entry):
                cfg._save_game_file(key)
        return cfg

    @classmethod
    def _migrate_from_legacy(cls) -> "Config":
        """One-time move from the old single settings.json to config.yaml + games/*.yaml.
        The old file is left in place untouched, as a safety net."""
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, json.JSONDecodeError):
            old = {}
        per_game = old.pop("per_game", {}) or {}

        cfg = cls(old)
        for key, entry in per_game.items():
            renamed = dict(entry)
            for old_field, new_field in _LEGACY_GAME_FIELDS.items():
                if old_field in renamed:
                    renamed[new_field] = renamed.pop(old_field)
            cfg._games[key] = renamed
        cfg.save()
        for key in cfg._games:
            cfg._save_game_file(key)
        return cfg

    def save(self) -> None:
        ensure_dirs()
        with self._lock:
            _atomic_write_yaml(CONFIG_FILE, self._data)

    def _filename_for(self, key: str, entry: dict[str, Any]) -> str:
        """The file's basename: the VN's title (picked or detected) once known, else
        its key. Disambiguated against whatever other games are currently using that name."""
        title = (entry.get("title") or entry.get("name") or "").strip()
        base = _safe_filename(title) if title else _safe_filename(key)
        candidate = base
        n = 2
        used = {v.lower() for k, v in self._game_filenames.items() if k != key}
        while candidate.lower() in used:
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def _save_game_file(self, key: str) -> None:
        with self._lock:
            self._save_game_file_locked(key)

    def _save_game_file_locked(self, key: str) -> None:
        entry = self._games.get(key)
        if entry is None:
            return
        new_stem = self._filename_for(key, entry)
        old_stem = self._game_filenames.get(key)
        if old_stem and old_stem.lower() != new_stem.lower():
            try:
                (GAMES_DIR / f"{old_stem}.yaml").unlink()
            except FileNotFoundError:
                pass
        to_write = dict(entry)
        to_write["_key"] = key
        _atomic_write_yaml(GAMES_DIR / f"{new_stem}.yaml", to_write)
        self._game_filenames[key] = new_stem

    def _delete_game_file(self, key: str) -> None:
        stem = self._game_filenames.pop(key, None) or _safe_filename(key)
        try:
            (GAMES_DIR / f"{stem}.yaml").unlink()
        except FileNotFoundError:
            pass

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def key_for(self, exe: str, exe_path: str = "") -> str:
        """The Library entry a running game belongs to. Games are told apart by the
        full path of their exe, because generic engine exes (cmvs64, SiglusEngine,
        BGI…) are shared by many VNs. Entries keep the plain exe-name key they've
        always had; a second game with the same exe gets ``"<exe>@<folder>"``."""
        stem = game_key(exe or exe_path)
        wanted = _norm_path(exe_path)
        if not wanted:
            return stem
        folder = _folder_name(exe_path)
        with self._lock:
            for key, entry in self._games.items():
                if _norm_path(entry.get("path")) == wanted:
                    return key
            for key, entry in self._games.items():
                if game_key(key.split("@", 1)[0]) != stem:
                    continue
                saved = entry.get("path")
                if not saved:
                    return key  # tracked before paths were saved
                if not os.path.exists(saved) and _folder_name(saved) == folder:
                    return key  # same game, moved somewhere else
            if stem not in self._games:
                return stem
            base = f"{stem}@{_safe_filename(folder) or 'game'}"
            candidate, n = base, 2
            while candidate in self._games:
                candidate, n = f"{base}_{n}", n + 1
            return candidate

    def game_override(self, key: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._games.get(key, {}))

    def all_games(self) -> dict[str, dict[str, Any]]:
        """Every tracked VN, keyed by its normalized id -- for the Library view."""
        with self._lock:
            return {k: dict(v) for k, v in self._games.items()}

    def known_game_paths(self) -> list[str]:
        """Saved exe paths of every tracked VN, so they're recognized straight away."""
        with self._lock:
            return [e["path"] for e in self._games.values() if isinstance(e.get("path"), str) and e["path"]]

    def set_game_override(self, key: str, **fields: Any) -> None:
        with self._lock:
            entry = self._games.setdefault(key, {})
            if fields.get("status") == "finished" and entry.get("status") != "finished":
                entry["finished_at"] = int(time.time())  # for "VNs finished this week"
            entry.update({k: v for k, v in fields.items() if v is not None})
            self._save_game_file_locked(key)

    def clear_game_override(self, key: str) -> None:
        with self._lock:
            if key in self._games:
                del self._games[key]
                self._playtime_frac.pop(key, None)
                self._delete_game_file(key)

    def get_playtime_seconds(self, key: str) -> int:
        with self._lock:
            return int(self._games.get(key, {}).get("playtime_seconds", 0))

    def add_playtime_seconds(self, key: str, seconds: float) -> None:
        if not key or seconds <= 0:
            return
        with self._lock:
            entry = self._games.setdefault(key, {})
            total = self._playtime_frac.get(key, 0.0) + seconds
            whole = int(total)
            self._playtime_frac[key] = total - whole
            entry["playtime_seconds"] = int(entry.get("playtime_seconds", 0)) + whole
            if whole:
                daily = entry.setdefault("daily", {})
                today = _day()
                daily[today] = int(daily.get(today, 0)) + whole
            entry["last_played"] = int(time.time())
            self._save_game_file_locked(key)

    def start_session(self, key: str) -> None:
        """A game just came into focus: count one more reading session."""
        if not key:
            return
        with self._lock:
            entry = self._games.setdefault(key, {})
            entry["sessions"] = int(entry.get("sessions", 0)) + 1
            entry["last_played"] = int(time.time())
            self._save_game_file_locked(key)

    def reset_playtime(self, key: str) -> None:
        with self._lock:
            entry = self._games.get(key)
            if entry is not None:
                for stat in ("playtime_seconds", "daily", "sessions"):
                    entry.pop(stat, None)
                self._playtime_frac.pop(key, None)
                self._save_game_file_locked(key)
