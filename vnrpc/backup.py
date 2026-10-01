from __future__ import annotations

import json
import os
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from . import __version__
from . import config as config_mod
from .config import Config
from .paths import APP_DIR, LOCAL_COVER_DIR

FORMAT = 1
_MANIFEST = "vnrpc-backup.json"
# Before an import replaces anything, what was there is saved here.
BACKUP_DIR = APP_DIR / "backups"


class BackupError(Exception):
    pass


def default_name() -> str:
    return time.strftime("VisualNovelRPC-backup-%Y-%m-%d.zip")


def export_data(cfg: Config, dest: Path) -> int:
    """Write the backup to ``dest``; returns how many VNs are in it."""
    with cfg.lock:
        data = dict(cfg.data)
        games = cfg.all_games()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    covers: dict[str, str] = {}
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("config.yaml", _dump(data))
            for n, (key, entry) in enumerate(sorted(games.items()), 1):
                zf.writestr(f"games/{n:04d}.yaml", _dump({**entry, "_key": key}))
                path = _local_cover(entry)
                if path is not None:
                    arc = f"covers/{n:04d}_{config_mod._safe_filename(path.name)}"
                    zf.write(path, arc)
                    covers[key] = arc
            zf.writestr(_MANIFEST, json.dumps({
                "format": FORMAT, "app_version": __version__,
                "exported_at": int(time.time()), "games": len(games), "covers": covers,
            }, indent=2))
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return len(games)


def import_data(cfg: Config, src: Path) -> int:
    """Replace the settings and Library with the backup's, then reload ``cfg``.
    A copy of what was there before goes to ``BACKUP_DIR`` first. Returns how
    many VNs were loaded; raises BackupError if ``src`` isn't a backup."""
    try:
        zf = zipfile.ZipFile(src)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(f"not a Visual Novel RPC backup ({exc})") from None
    with zf:
        manifest = _manifest(zf)
        data = _load(zf, "config.yaml")
        games: dict[str, dict[str, Any]] = {}
        for name in zf.namelist():
            if name.startswith("games/") and name.endswith(".yaml"):
                entry = _load(zf, name)
                key = entry.pop("_key", None)
                if isinstance(key, str) and key:
                    games[key] = entry
        cover_files = {key: zf.read(arc) for key, arc in (manifest.get("covers") or {}).items()
                       if key in games and arc in zf.namelist()}
        cover_names = {key: PurePosixPath(arc).name for key, arc in (manifest.get("covers") or {}).items()
                       if key in cover_files}

    export_data(cfg, BACKUP_DIR / time.strftime("before-import-%Y-%m-%d_%H-%M-%S.zip"))

    with cfg.lock:
        LOCAL_COVER_DIR.mkdir(parents=True, exist_ok=True)
        for key, blob in cover_files.items():
            # The covers live in this PC's app folder now, wherever the old one was.
            dest = LOCAL_COVER_DIR / config_mod._safe_filename(cover_names[key])
            dest.write_bytes(blob)
            games[key]["cover_value"] = str(dest)

        games_dir: Path = config_mod.GAMES_DIR
        games_dir.mkdir(parents=True, exist_ok=True)
        for old in games_dir.glob("*.yaml"):
            old.unlink()
        used: set[str] = set()
        for key, entry in games.items():
            stem = base = config_mod._safe_filename(entry.get("title") or entry.get("name") or key)
            n = 2
            while stem.lower() in used:
                stem, n = f"{base}_{n}", n + 1
            used.add(stem.lower())
            config_mod._atomic_write_yaml(games_dir / f"{stem}.yaml", {**entry, "_key": key})
        config_mod._atomic_write_yaml(config_mod.CONFIG_FILE, data)
        cfg.reload()
    return len(games)


def _manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        manifest = json.loads(zf.read(_MANIFEST))
    except (KeyError, ValueError):
        raise BackupError("not a Visual Novel RPC backup") from None
    if not isinstance(manifest, dict) or int(manifest.get("format") or 0) > FORMAT:
        raise BackupError("this backup was made by a newer version of the app: update it first")
    if "config.yaml" not in zf.namelist():
        raise BackupError("the backup is missing its settings")
    return manifest


def _load(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(zf.read(name)) or {}
    except yaml.YAMLError as exc:
        raise BackupError(f"{name} is damaged ({exc})") from None
    return value if isinstance(value, dict) else {}


def _dump(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)


def _local_cover(entry: dict[str, Any]) -> Path | None:
    if entry.get("cover_source") != "local":
        return None
    value = entry.get("cover_value")
    path = Path(value) if isinstance(value, str) and value else None
    return path if path is not None and path.is_file() else None
