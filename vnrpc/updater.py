from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

from . import __version__

REPO = "lennmoe/vnrpc"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_HEADERS = {"User-Agent": f"VisualNovelRPC/{__version__}", "Accept": "application/vnd.github+json"}


@dataclass
class Release:
    version: str
    url: str  # the .exe asset
    size: int
    sha256: str  # "" when GitHub didn't give a digest
    notes: str
    page: str


def supported() -> bool:
    """Only the packaged .exe can replace itself; from source there's nothing to swap."""
    return bool(getattr(sys, "frozen", False))


def parse_version(tag: str) -> tuple[int, ...]:
    """"v1.2.1" / "1.2.1" -> (1, 2, 1). Anything that isn't a version -> ()."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", tag or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def is_newer(tag: str, current: str = __version__) -> bool:
    new, cur = parse_version(tag), parse_version(current)
    if not new:
        return False
    width = max(len(new), len(cur))
    return new + (0,) * (width - len(new)) > cur + (0,) * (width - len(cur))


def find_update(current: str = __version__, session: requests.Session | None = None) -> Release | None:
    """The latest GitHub release if it's newer than ``current`` and has an .exe attached."""
    resp = (session or requests).get(_API, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("draft") or data.get("prerelease") or not is_newer(data.get("tag_name", ""), current):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    if asset is None:
        return None
    digest = asset.get("digest") or ""
    return Release(
        version=data["tag_name"].lstrip("vV"),
        url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "",
        notes=(data.get("body") or "").strip(),
        page=data.get("html_url") or f"https://github.com/{REPO}/releases/latest",
    )


def download(release: Release, dest: Path) -> Path:
    """Fetch the release's .exe to ``dest``, checking its size and hash."""
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with requests.get(release.url, headers=_HEADERS, timeout=30, stream=True) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(1 << 16):
                f.write(chunk)
                h.update(chunk)
    size = tmp.stat().st_size
    if (release.size and size != release.size) or (release.sha256 and h.hexdigest() != release.sha256):
        tmp.unlink(missing_ok=True)
        raise OSError("the downloaded file is incomplete or corrupted")
    os.replace(tmp, dest)
    return dest


def _clean_env() -> dict[str, str]:
    """Our environment minus what the PyInstaller bootloader set for *this* run,
    so the restarted .exe unpacks itself fresh instead of reusing our temp dir."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("_PYI") and k not in ("_MEIPASS2", "TCL_LIBRARY", "TK_LIBRARY")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def install(new_exe: Path, target: Path | None = None) -> None:
    """Start the helper that replaces ``target`` (this .exe) with ``new_exe`` and
    relaunches it. The caller must quit right after."""
    target = target or Path(sys.executable)
    script = Path(tempfile.gettempdir()) / "vnrpc_update.cmd"
    # `move` fails while the old .exe is still running: retry once a second for ~1 min.
    script.write_text(
        "@echo off\r\n"
        "set tries=0\r\n"
        ":wait\r\n"
        f'move /y "{new_exe}" "{target}" >nul 2>&1 && goto run\r\n'
        "set /a tries+=1\r\n"
        "if %tries% geq 60 goto end\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        "goto wait\r\n"
        ":run\r\n"
        f'start "" "{target}"\r\n'
        ":end\r\n"
        'del "%~f0"\r\n',
        encoding="mbcs",
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        env=_clean_env(),
        cwd=str(target.parent),
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def staging_path(target: Path | None = None) -> Path:
    """Where the new .exe is downloaded: next to the current one, so the final
    move is a cheap rename on the same drive."""
    target = target or Path(sys.executable)
    return target.with_name(target.stem + ".new.exe")
