from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

_winmm = ctypes.WinDLL("winmm")
_winmm.mciSendStringW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
_winmm.mciSendStringW.restype = wintypes.DWORD


class Sound:
    """A short sound file played through Windows' MCI, which reads MP3 (and WAV)
    without any extra package. The file is opened on the first play and kept open
    so later plays start instantly. Use it from one thread (the Tk one)."""

    def __init__(self, path: Path, alias: str) -> None:
        self._path = path
        self._alias = alias
        self._open = False
        self._broken = False  # missing file or no audio device: stay silent

    def play(self, volume: int = 100) -> None:
        """``volume``: 0-100 (% of the file's own loudness)."""
        if self._broken or volume <= 0:
            return
        if not self._open:
            kind = "mpegvideo" if self._path.suffix.lower() == ".mp3" else "waveaudio"
            if not self._path.is_file() or _mci(f'open "{self._path}" type {kind} alias {self._alias}'):
                self._broken = True
                return
            self._open = True
        _mci(f"setaudio {self._alias} volume to {min(100, int(volume)) * 10}")
        _mci(f"play {self._alias} from 0")

    def close(self) -> None:
        if self._open:
            _mci(f"close {self._alias}")
            self._open = False


def _mci(command: str) -> int:
    """0 on success, else MCI's error code."""
    return _winmm.mciSendStringW(command, None, 0, None)
