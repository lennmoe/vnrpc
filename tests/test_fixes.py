import os
import time

import pytest

from vnrpc import config as config_mod
from vnrpc import window_watcher
from vnrpc.config import DEFAULTS, Config
from vnrpc.core import Snapshot, VNRPCEngine
from vnrpc.engines import blacklist_set, is_blacklisted
from vnrpc.title_parser import DEFAULT_RULES, build_rules
from vnrpc.winapi import WindowInfo
from vnrpc.window_watcher import WindowWatcher


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    return Config()


def test_playtime_keeps_fractional_seconds(cfg):
    for _ in range(4):
        cfg.add_playtime_seconds("game", 0.5)
    assert cfg.get_playtime_seconds("game") == 2


def test_no_playtime_banked_while_paused(cfg):
    engine = VNRPCEngine(cfg)
    engine._playtime_key = "game"
    engine._playtime_tick_start = time.time() - 30
    engine.set_paused(True)
    assert cfg.get_playtime_seconds("game") == 30
    engine._playtime_tick_start = time.time() - 600
    engine._flush_playtime()
    assert cfg.get_playtime_seconds("game") == 30


def test_build_rules_skips_malformed_entries():
    rules = build_rules([
        "not a dict",
        {"label": "no pattern"},
        {"pattern": "(unclosed"},
        {"name": "ok", "pattern": r"part\s*(?P<n>\d+)", "label": "Part {n}"},
    ])
    assert [r.name for r in rules[: len(rules) - len(DEFAULT_RULES)]] == ["ok"]


def test_activity_respects_privacy(cfg):
    engine = VNRPCEngine(cfg)
    snap = Snapshot(detected=True, game_name="Sugar*Style", section_label="Chapter 2", session_start=100)
    assert engine.activity_for(snap).details == "Reading — Chapter 2"
    snap.privacy = "partial"
    assert engine.activity_for(snap).details == ""
    snap.privacy = "private"
    assert engine.activity_for(snap).name == "Visual Novel"
    snap.privacy = "off"
    assert engine.activity_for(snap) is None
    assert engine.activity_for(Snapshot()) is None


def _win(exe_path: str, class_name: str = "") -> WindowInfo:
    return WindowInfo(hwnd=1, title="Some window", pid=1, exe_path=exe_path, class_name=class_name)


def test_user_blacklist_is_normalized():
    bl = blacklist_set(["osu!", r"C:\Apps\Medal.EXE", ""])
    assert is_blacklisted("osu!.exe", bl)
    assert is_blacklisted("medal.exe", bl)
    assert is_blacklisted("discord.exe", bl)
    assert not is_blacklisted("BGI.exe", bl)


def test_blacklisted_window_is_never_picked(monkeypatch):
    vn = _win(r"C:\vn\krkr.exe", class_name="TForm")
    picked = []
    watcher = WindowWatcher(picked.append)
    assert watcher._pick_auto([vn])[0] is vn
    watcher.configure(mode="auto", blacklist=blacklist_set(["krkr.exe"]))
    monkeypatch.setattr(window_watcher, "list_top_level_windows", lambda: [vn])
    watcher._tick()
    assert picked == []


def test_library_game_is_detected_by_saved_path():
    game = _win(r"C:\vn\Sakura\sakura.exe")
    watcher = WindowWatcher(lambda _t: None)
    assert watcher._pick_auto([game]) is None
    known = frozenset({os.path.normcase(r"c:\VN\sakura\SAKURA.exe")})
    assert watcher._pick_auto([game], known)[0] is game


def test_add_to_blacklist_does_not_touch_defaults(cfg):
    engine = VNRPCEngine(cfg)
    before = list(DEFAULTS["blacklist_exe"])
    engine.add_to_blacklist("RiotClientServices.exe")
    engine.add_to_blacklist("riotclientservices")
    assert cfg["blacklist_exe"] == before + ["RiotClientServices.exe"]
    assert DEFAULTS["blacklist_exe"] == before
    assert "riotclientservices.exe" in engine.blacklist



def test_presence_lines_can_be_turned_off(cfg):
    engine = VNRPCEngine(cfg)
    snap = Snapshot(detected=True, game_name="Hapymaher", section_label="Chapter 1",
                    playtime_seconds=3600, playtime_text="1h 00m")
    act = engine.activity_for(snap)
    assert act.details == "Reading — Chapter 1" and act.state == "Total read: 1h 00m"
    cfg["show_section"] = False
    cfg["show_total_read"] = False
    act = engine.activity_for(snap)
    assert act.details == "" and act.state == ""
    assert act.name == "Hapymaher"


class _FakeDesktop:
    """Stands in for the Win32 calls the watcher makes."""

    def __init__(self, monkeypatch, windows):
        self.windows = list(windows)
        self.hidden: set[int] = set()
        monkeypatch.setattr(window_watcher, "list_top_level_windows",
                            lambda: [w for w in self.windows if w.hwnd not in self.hidden])
        monkeypatch.setattr(window_watcher, "is_window_visible",
                            lambda hwnd: any(w.hwnd == hwnd for w in self.windows) and hwnd not in self.hidden)
        monkeypatch.setattr(window_watcher, "get_window_title",
                            lambda hwnd: next((w.title for w in self.windows if w.hwnd == hwnd), ""))


def _vn_window():
    return WindowInfo(hwnd=7, title="hapymaher - Chapter 1", pid=7, exe_path=r"C:\vn\krkr.exe",
                      class_name="TForm")


def test_game_that_hides_its_window_on_exit_counts_as_closed(monkeypatch):
    desk = _FakeDesktop(monkeypatch, [_vn_window()])
    events = []
    watcher = WindowWatcher(events.append)
    watcher._tick()
    assert events[-1].raw_title == "hapymaher - Chapter 1"
    desk.hidden.add(7)  # window hidden while the process lingers
    for _ in range(window_watcher._GONE_AFTER):
        watcher._tick()
    assert events[-1] is None


def test_brief_disappearance_does_not_drop_the_game(monkeypatch):
    desk = _FakeDesktop(monkeypatch, [_vn_window()])
    events = []
    watcher = WindowWatcher(events.append)
    watcher._tick()
    desk.hidden.add(7)
    watcher._tick()
    desk.hidden.clear()
    watcher._tick()
    assert None not in events


def test_closing_is_reported_even_right_after_a_poke(monkeypatch):
    desk = _FakeDesktop(monkeypatch, [_vn_window()])
    events = []
    watcher = WindowWatcher(events.append)
    watcher._tick()
    watcher.poke()  # e.g. settings saved
    desk.windows.clear()
    for _ in range(window_watcher._GONE_AFTER):
        watcher._tick()
    assert events[-1] is None


def test_closing_is_retried_if_handling_it_fails(monkeypatch):
    desk = _FakeDesktop(monkeypatch, [_vn_window()])
    events = []

    def on_change(target):
        if target is None and not events.count("failed"):
            events.append("failed")
            raise OSError("file locked")
        events.append(target)

    watcher = WindowWatcher(on_change)
    watcher._tick()
    desk.windows.clear()
    for _ in range(window_watcher._GONE_AFTER - 1):
        watcher._tick()
    with pytest.raises(OSError):
        watcher._tick()  # 3rd miss: first attempt to report the close fails
    watcher._tick()
    assert events[-1] is None
