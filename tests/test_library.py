import datetime as dt
import os

import pytest

from vnrpc import config as config_mod
from vnrpc import stats
from vnrpc.config import Config
from vnrpc.engines import detect_engine
from vnrpc.vndb import push_list_status
from vnrpc.winapi import WindowInfo


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    return Config()


def _exe(tmp_path, folder: str, name: str = "cmvs64.exe") -> str:
    path = tmp_path / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return str(path)


def test_same_exe_name_in_two_folders_gives_two_games(cfg, tmp_path):
    hapymaher = _exe(tmp_path, "Hapymaher")
    amatsutsumi = _exe(tmp_path, "Amatsutsumi")
    key = cfg.key_for("cmvs64.exe", hapymaher)
    assert key == "cmvs64"
    cfg.set_game_override(key, path=hapymaher)

    other = cfg.key_for("cmvs64.exe", amatsutsumi)
    assert other == "cmvs64@amatsutsumi"
    cfg.set_game_override(other, path=amatsutsumi)
    assert cfg.key_for("cmvs64.exe", hapymaher) == "cmvs64"
    assert cfg.key_for("CMVS64.exe", amatsutsumi.upper()) == "cmvs64@amatsutsumi"


def test_entry_saved_before_paths_existed_is_adopted(cfg, tmp_path):
    cfg.add_playtime_seconds("siglusengine", 120)
    assert cfg.key_for("SiglusEngine.exe", _exe(tmp_path, "Sayonara", "SiglusEngine.exe")) == "siglusengine"


def test_moved_game_keeps_its_entry(cfg, tmp_path):
    cfg.set_game_override("cmvs64", path=str(tmp_path / "Downloads" / "Hapymaher" / "cmvs64.exe"))
    moved = _exe(tmp_path, os.path.join("vn", "Hapymaher"))
    assert cfg.key_for("cmvs64.exe", moved) == "cmvs64"
    # …but a different game that merely shares the exe name doesn't take it over.
    assert cfg.key_for("cmvs64.exe", _exe(tmp_path, "Kinkoi")) == "cmvs64@kinkoi"


def test_no_path_falls_back_to_exe_name(cfg):
    assert cfg.key_for("BGI.exe", "") == "bgi"


def test_playtime_is_also_logged_per_day(cfg):
    cfg.add_playtime_seconds("game", 90)
    cfg.add_playtime_seconds("game", 30)
    entry = cfg.game_override("game")
    assert entry["daily"] == {dt.date.today().isoformat(): 120}
    assert entry["last_played"] > 0


def test_sessions_are_counted_and_reset_with_playtime(cfg):
    cfg.start_session("game")
    cfg.start_session("game")
    cfg.add_playtime_seconds("game", 60)
    assert cfg.game_override("game")["sessions"] == 2
    cfg.reset_playtime("game")
    entry = cfg.game_override("game")
    assert "sessions" not in entry and "daily" not in entry and "playtime_seconds" not in entry


def test_daily_and_weekly_series():
    today = dt.date(2026, 9, 30)  # a Wednesday
    daily = {"2026-09-30": 600, "2026-09-28": 60, "2026-09-27": 300, "2026-06-01": 999, "junk": 5}
    days = stats.daily_series(daily, 3, today)
    assert days == [(dt.date(2026, 9, 28), 60), (dt.date(2026, 9, 29), 0), (dt.date(2026, 9, 30), 600)]
    weeks = stats.weekly_series(daily, 2, today)
    assert weeks == [(dt.date(2026, 9, 21), 300), (dt.date(2026, 9, 28), 660)]
    assert stats.this_week_seconds(daily, today) == 660
    assert stats.first_day(daily) == dt.date(2026, 6, 1)


def test_last_played_text():
    now = dt.datetime(2026, 9, 30, 12).timestamp()
    day = 86400
    assert stats.last_played_text(now - 60, now) == "today"
    assert stats.last_played_text(now - day, now) == "yesterday"
    assert stats.last_played_text(now - 3 * day, now) == "3 days ago"
    assert stats.last_played_text(dt.datetime(2026, 9, 1, 12).timestamp(), now) == "1 Sep"
    assert stats.last_played_text(dt.datetime(2025, 9, 1, 12).timestamp(), now) == "1 Sep 2025"
    assert stats.last_played_text(0, now) == ""


def test_window_class_alone_is_not_a_vn(tmp_path):
    medal = WindowInfo(hwnd=1, title="Medal", pid=1, exe_path=_exe(tmp_path, "Medal", "Medal.exe"),
                       class_name="Chrome_WidgetWin_1")
    osu = WindowInfo(hwnd=2, title="osu!", pid=2, exe_path=_exe(tmp_path, "osu", "osu!.exe"),
                     class_name="SDL_app")
    assert detect_engine(medal) == (None, 0)
    assert detect_engine(osu) == (None, 0)


def test_window_class_still_helps_a_real_engine(tmp_path):
    exe = _exe(tmp_path, "Katawa", "Katawa Shoujo.exe")
    (tmp_path / "Katawa" / "archive.rpa").write_bytes(b"")
    engine, score = detect_engine(WindowInfo(hwnd=1, title="Katawa Shoujo", pid=1, exe_path=exe,
                                             class_name="SDL_app"))
    assert engine.name == "Ren'Py" and score == 45


class FakeVNDB:
    def __init__(self, entry=None):
        self.entry = entry
        self.patches = []

    def get_list_entry(self, token, vn_id):
        return self.entry

    def update_list_entry(self, token, vn_id, changes):
        self.patches.append((vn_id, changes))


def test_new_vn_is_added_as_playing():
    client = FakeVNDB()
    assert push_list_status(client, "tok", "v1200", "playing", keep_existing=True) == "playing"
    (vn_id, changes), = client.patches
    assert vn_id == "v1200"
    assert changes["labels_set"] == [1]
    assert changes["labels_unset"] == [2, 3, 4]
    assert "started" in changes and "finished" not in changes


def test_existing_list_status_is_kept_on_auto_sync():
    client = FakeVNDB({"labels": [{"id": 2}, {"id": 7}], "started": "2024-01-01", "finished": "2024-02-01"})
    assert push_list_status(client, "tok", "v1200", "playing", keep_existing=True) == "finished"
    assert client.patches == []


def test_finishing_sets_the_label_and_the_date():
    client = FakeVNDB({"labels": [{"id": 1}], "started": "2026-09-01"})
    assert push_list_status(client, "tok", "v1200", "finished") == "finished"
    (_, changes), = client.patches
    assert changes["labels_set"] == [2] and changes["labels_unset"] == [1, 3, 4]
    assert "finished" in changes and "started" not in changes


def _engine(cfg, monkeypatch, vn=None):
    from vnrpc.core import VNRPCEngine

    cfg["use_steam_names"] = False
    engine = VNRPCEngine(cfg)
    monkeypatch.setattr(engine.vndb, "search_vn", lambda *a, **k: [vn] if vn else [])
    monkeypatch.setattr(engine.vndb, "get_vn", lambda vn_id: vn)
    monkeypatch.setattr(engine.vndb, "cover_path", lambda *a: None)
    return engine


def test_engine_keeps_two_games_with_the_same_exe_apart(cfg, tmp_path, monkeypatch):
    from vnrpc.window_watcher import TargetState

    engine = _engine(cfg, monkeypatch)
    first, second = _exe(tmp_path, "Hapymaher"), _exe(tmp_path, "Amatsutsumi")
    engine._handle_target(TargetState(1, 1, "cmvs64.exe", first, "hapymaher - Chapter 1"))
    engine._handle_target(TargetState(2, 2, "cmvs64.exe", second, "Amatsutsumi - Prologue"))
    engine._handle_target(TargetState(1, 1, "cmvs64.exe", first, "hapymaher - Chapter 2"))
    games = cfg.all_games()
    assert games["cmvs64"]["path"] == first and games["cmvs64"]["sessions"] == 2
    assert games["cmvs64@amatsutsumi"]["path"] == second
    assert games["cmvs64@amatsutsumi"]["status"] == "playing"
    assert engine.snapshot.key == "cmvs64"


def test_engine_syncs_a_confirmed_vn_once(cfg, tmp_path, monkeypatch):
    import threading

    from vnrpc import core
    from vnrpc.vndb import VNResult
    from vnrpc.window_watcher import TargetState

    vn = VNResult(id="v1200", title="Sayonara o Oshiete")
    engine = _engine(cfg, monkeypatch, vn)
    calls = []

    def fake_push(client, token, vn_id, status, *, keep_existing):
        calls.append((token, vn_id, status, keep_existing))
        return "finished"

    monkeypatch.setattr(core, "push_list_status", fake_push)
    monkeypatch.setattr(threading.Thread, "start", lambda self: self.run())
    exe = _exe(tmp_path, "Sayonara", "SiglusEngine.exe")
    target = TargetState(1, 1, "SiglusEngine.exe", exe, "Sayonara wo Oshiete Day 10")

    engine._handle_target(target)
    assert calls == []  # sync is off
    cfg["vndb_sync"], cfg["vndb_token"] = True, "tok"
    engine._handle_target(target)
    assert calls == []  # only an automatic match: nothing is synced until it's confirmed
    engine.confirm_vn_match("siglusengine")
    engine._handle_target(target)
    engine._handle_target(TargetState(1, 1, "SiglusEngine.exe", exe, "Sayonara wo Oshiete Day 11"))
    assert calls == [("tok", "v1200", "playing", True)]
    entry = cfg.game_override("siglusengine")
    assert entry["vndb_synced"] == "v1200" and entry["status"] == "finished"

    engine.set_game_status("siglusengine", "dropped")
    assert calls[-1] == ("tok", "v1200", "dropped", False)


def test_unchanged_status_sends_nothing():
    client = FakeVNDB({"labels": [{"id": 3}]})
    assert push_list_status(client, "tok", "v1", "stalled") == "stalled"
    assert client.patches == []


def test_clearing_the_status_takes_the_labels_off():
    client = FakeVNDB({"labels": [{"id": 2}, {"id": 7}]})
    assert push_list_status(client, "tok", "v1", "") == ""
    assert client.patches == [("v1", {"labels_unset": [1, 2, 3, 4]})]


def test_clearing_a_vn_that_is_not_on_the_list_does_not_add_it():
    client = FakeVNDB(None)
    assert push_list_status(client, "tok", "v1", "") == ""
    assert client.patches == []


def test_cleared_status_is_not_set_back_to_playing(cfg, tmp_path, monkeypatch):
    from vnrpc.window_watcher import TargetState

    engine = _engine(cfg, monkeypatch)
    exe = _exe(tmp_path, "Hapymaher")
    engine._handle_target(TargetState(1, 1, "cmvs64.exe", exe, "hapymaher - Chapter 1"))
    assert cfg.game_override("cmvs64")["status"] == "playing"
    engine.set_game_status("cmvs64", "")
    engine._handle_target(TargetState(1, 1, "cmvs64.exe", exe, "hapymaher - Chapter 2"))
    assert cfg.game_override("cmvs64")["status"] == ""
