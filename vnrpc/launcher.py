"""Starting a Library game, directly or through a Japanese-locale tool (for VNs
that show garbled text or crash on a non-Japanese Windows)."""
from __future__ import annotations

import os
import subprocess

from .config import Config

NORMAL, LOCALE_EMULATOR, NTLEA = "", "le", "ntlea"
LAUNCHERS = (NORMAL, LOCALE_EMULATOR, NTLEA)
LABELS = {NORMAL: "Normal", LOCALE_EMULATOR: "Locale Emulator", NTLEA: "NTLEA"}
# Where each tool's exe is remembered in config.yaml, and what it's called.
TOOL_SETTING = {LOCALE_EMULATOR: "locale_emulator_path", NTLEA: "ntlea_path"}
TOOL_EXE = {LOCALE_EMULATOR: "LEProc.exe", NTLEA: "ntleas.exe"}


class ToolMissing(Exception):
    """The game is set to start through a tool whose exe isn't set or is gone."""

    def __init__(self, launcher: str) -> None:
        super().__init__(f"{LABELS[launcher]} ({TOOL_EXE[launcher]}) wasn't found.")
        self.launcher = launcher


def tool_path(config: Config, launcher: str) -> str:
    """The tool's exe if it's set and still there, else ``""``."""
    path = (config.get(TOOL_SETTING.get(launcher, "")) or "").strip()
    return path if path and os.path.isfile(path) else ""


def command(exe_path: str, launcher: str, tool: str = "") -> list[str] | None:
    """The command line that starts ``exe_path``; ``None`` to just open it."""
    if launcher == LOCALE_EMULATOR:
        # Uses the game's own LE profile if one was made, else LE's default (Japanese).
        return [tool, exe_path]
    if launcher == NTLEA:
        return [tool, exe_path, "C932", "L1041"]  # Shift-JIS code page, Japanese locale
    return None


def launch(config: Config, entry: dict) -> None:
    """Start the game of Library ``entry``. Raises FileNotFoundError when its exe is
    gone, ToolMissing when its locale tool is, and OSError if Windows refuses."""
    exe_path = entry.get("path") or ""
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(exe_path)
    launcher = entry.get("launcher") or NORMAL
    if launcher not in LAUNCHERS:
        launcher = NORMAL
    tool = tool_path(config, launcher) if launcher != NORMAL else ""
    if launcher != NORMAL and not tool:
        raise ToolMissing(launcher)
    cmd = command(exe_path, launcher, tool)
    cwd = os.path.dirname(exe_path)
    if cmd is None:
        os.startfile(exe_path, cwd=cwd)
    else:
        subprocess.Popen(cmd, cwd=cwd, close_fds=True)
