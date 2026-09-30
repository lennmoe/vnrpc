"""Screenshots, one folder per VN: ``<root>/<VN title>/2026-09-30 21-14-03.png``.

A VN's folder name is picked the first time it gets a screenshot and saved in its
Library entry (``screenshot_folder``), so renaming the VN later doesn't orphan it."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .config import Config
from .paths import THUMB_CACHE_DIR
from .winapi import pictures_folder, send_to_recycle_bin

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_STAMP = "%Y-%m-%d %H-%M-%S"


@dataclass
class ShotInfo:
    path: Path
    taken: dt.datetime
    width: int = 0
    height: int = 0
    section: str = ""


def default_root() -> Path:
    return Path(pictures_folder()) / "Visual Novel RPC"


def root(config: Config) -> Path:
    custom = (config.get("screenshot_dir") or "").strip()
    return Path(custom) if custom else default_root()


def hotkey_hint(config: Config) -> str:
    key = (config.get("screenshot_hotkey") or "").strip()
    if key:
        return f"Press {key} while reading to capture the game's window."
    return "Pick a screenshot key in Settings to capture the game's window."


def folder_name(title: str, taken: set[str] = frozenset()) -> str:
    """A Windows-safe folder name for ``title``, not in ``taken`` (compared
    case-insensitively): ``"Amatsutsumi"``, then ``"Amatsutsumi (2)"``…"""
    name = re.sub(r"\s+", " ", _INVALID.sub("", title or "")).strip()[:80].rstrip(". ")
    if not name or name.split(".")[0].upper() in _RESERVED:
        name = f"{name}_" if name else "Game"
    lowered = {t.lower() for t in taken}
    candidate, n = name, 2
    while candidate.lower() in lowered:
        candidate, n = f"{name} ({n})", n + 1
    return candidate


def folder_for(config: Config, key: str, *, create: bool = False) -> Path | None:
    """The VN's screenshot folder; ``None`` if it has never had one and ``create`` is off."""
    entry = config.game_override(key)
    name = entry.get("screenshot_folder")
    if not name:
        if not create:
            return None
        taken = {e.get("screenshot_folder") or "" for k, e in config.all_games().items() if k != key}
        name = folder_name(entry.get("title") or entry.get("name") or key, taken)
        config.set_game_override(key, screenshot_folder=name)
    path = root(config) / name
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def list_shots(folder: Path | None) -> list[Path]:
    """Images in ``folder``, newest first."""
    if folder is None or not folder.is_dir():
        return []
    shots = []
    for entry in os.scandir(folder):
        if entry.is_file() and entry.name.lower().endswith(IMAGE_EXTS):
            shots.append((entry.stat().st_mtime, entry.name, Path(entry.path)))
    shots.sort(reverse=True)
    return [path for _, _, path in shots]


def save(img: Image.Image, folder: Path, *, game: str = "", section: str = "",
         when: dt.datetime | None = None) -> Path:
    """Write ``img`` as a PNG named after ``when`` (default: now). The game and the
    part of the story it was taken in are kept inside the file."""
    when = when or dt.datetime.now()
    folder.mkdir(parents=True, exist_ok=True)
    stem = when.strftime(_STAMP)
    path, n = folder / f"{stem}.png", 2
    while path.exists():
        path, n = folder / f"{stem} ({n}).png", n + 1
    meta = PngInfo()
    meta.add_text("Creation Time", when.isoformat(timespec="seconds"))
    meta.add_text("Software", "Visual Novel RPC")
    if game:
        meta.add_itxt("Title", game)
    if section:
        meta.add_itxt("Section", section)
    tmp = path.with_suffix(".png.part")
    img.save(tmp, "PNG", pnginfo=meta, compress_level=6)
    os.replace(tmp, path)
    return path


def info(path: Path) -> ShotInfo:
    """What's known about a screenshot, read from its header only (cheap)."""
    try:
        taken = dt.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        taken = dt.datetime.now()
    try:
        with Image.open(path) as im:
            width, height = im.size
            meta = dict(im.info)
    except Exception:
        return ShotInfo(path, taken)
    try:
        taken = dt.datetime.fromisoformat(str(meta.get("Creation Time", "")))
    except ValueError:
        pass
    return ShotInfo(path, taken, width, height, str(meta.get("Section") or ""))


def thumbnail(path: Path, size: tuple[int, int]) -> Image.Image | None:
    """``path`` cover-fitted to ``size``, from the disk cache when it's there."""
    try:
        st = path.stat()
    except OSError:
        return None
    tag = f"{path}|{st.st_mtime_ns}|{st.st_size}|{size[0]}x{size[1]}".encode("utf-8")
    cached = THUMB_CACHE_DIR / f"{hashlib.sha1(tag).hexdigest()[:24]}.jpg"
    try:
        with Image.open(cached) as im:
            return im.convert("RGB")
    except Exception:
        pass
    try:
        with Image.open(path) as im:
            im.draft("RGB", (size[0] * 2, size[1] * 2))  # JPEGs decode at a fraction of full size
            thumb = _cover_fit(im.convert("RGB"), size)
    except Exception:
        return None
    try:
        THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        thumb.save(cached, "JPEG", quality=88)
    except OSError:
        pass
    return thumb


def delete(path: Path) -> None:
    """Send a screenshot to the Recycle Bin. Raises OSError."""
    send_to_recycle_bin(str(path))


def _cover_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


_listeners: list[Callable[[str], None]] = []


def subscribe(fn: Callable[[str], None]) -> None:
    _listeners.append(fn)


def unsubscribe(fn: Callable[[str], None]) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def notify(key: str) -> None:
    """``key``: the Library entry whose screenshots changed."""
    for fn in list(_listeners):
        try:
            fn(key)
        except Exception:
            pass
