import datetime as dt
import time

import pytest

from vnrpc import config as config_mod
from vnrpc import launcher, share_card
from vnrpc.config import Config

TODAY = dt.date(2026, 9, 30)  # a Wednesday
PALETTE = {"BG": "#111214", "SURFACE": "#1B1C20", "SURFACE_ALT": "#232428", "BORDER": "#2E3035",
           "TEXT": "#F2F3F5", "MUTED": "#A0A3A8", "SUBTLE": "#6D7076", "ACCENT": "#5865F2", "GREEN": "#23A55A"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    return Config()


def _stamp(day: dt.date) -> int:
    return int(time.mktime(day.timetuple())) + 12 * 3600


def test_periods():
    assert share_card.period(share_card.THIS_WEEK, TODAY) == (dt.date(2026, 9, 28), dt.date(2026, 10, 4))
    assert share_card.period(share_card.LAST_WEEK, TODAY) == (dt.date(2026, 9, 21), dt.date(2026, 9, 27))
    assert share_card.period(share_card.THIS_MONTH, TODAY) == (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert share_card.period(share_card.LAST_MONTH, dt.date(2026, 1, 15)) == (dt.date(2025, 12, 1),
                                                                             dt.date(2025, 12, 31))


def test_collect_counts_only_the_period():
    games = {
        "a": {"title": "Hapymaher", "daily": {"2026-09-28": 3600, "2026-09-30": 1800, "2026-09-27": 999}},
        "b": {"name": "Amatsutsumi", "daily": {"2026-09-29": 600}},
        "c": {"name": "Old one", "daily": {"2026-08-01": 5000}},
    }
    data = share_card.collect(games, share_card.THIS_WEEK, TODAY)
    assert [vn.name for vn in data.vns] == ["Hapymaher", "Amatsutsumi"]
    assert data.total_seconds == 6000
    assert (data.days_read, data.days_so_far) == (3, 3)
    assert len(data.daily) == 7
    assert data.title == "My week in visual novels" and data.subtitle == "28 Sep – 4 Oct 2026"
    month = share_card.collect(games, share_card.THIS_MONTH, TODAY)
    assert month.title == "My September in visual novels" and month.total_seconds == 6999


def test_finished_in_the_period():
    games = {
        "done": {"name": "Done", "status": "finished", "finished_at": _stamp(dt.date(2026, 9, 29))},
        "earlier": {"name": "Earlier", "status": "finished", "finished_at": _stamp(dt.date(2026, 8, 3))},
        # Finished before finish dates were saved: the last time it was read stands in.
        "legacy": {"name": "Legacy", "status": "finished", "last_played": _stamp(dt.date(2026, 9, 28))},
        "reading": {"name": "Reading", "status": "playing", "finished_at": _stamp(dt.date(2026, 9, 29))},
    }
    data = share_card.collect(games, share_card.THIS_WEEK, TODAY)
    assert sorted(vn.name for vn in data.finished) == ["Done", "Legacy"]


def test_finish_date_is_saved_when_status_becomes_finished(cfg):
    cfg.set_game_override("g", status="playing")
    assert "finished_at" not in cfg.game_override("g")
    cfg.set_game_override("g", status="finished")
    first = cfg.game_override("g")["finished_at"]
    assert abs(first - time.time()) < 5
    cfg.set_game_override("g", status="finished", playtime_seconds=3)  # already finished: kept
    assert cfg.game_override("g")["finished_at"] == first


def test_render_makes_a_card(tmp_path):
    games = {
        "a": {"title": "千恋＊万花", "daily": {"2026-09-29": 7200}, "status": "finished",
              "finished_at": _stamp(dt.date(2026, 9, 29))},
        "b": {"title": "A very long visual novel title that has to be cut somewhere", "daily": {"2026-09-30": 60},
              "cover_source": "local", "cover_value": str(tmp_path / "missing.png")},
    }
    img = share_card.render(share_card.collect(games, share_card.THIS_WEEK, TODAY), PALETTE)
    assert img.size == share_card.SIZE
    empty = share_card.render(share_card.collect({}, share_card.LAST_MONTH, TODAY), PALETTE)
    assert empty.size == share_card.SIZE


def test_launch_commands():
    assert launcher.command(r"C:\vn\game.exe", launcher.NORMAL) is None
    assert launcher.command(r"C:\vn\game.exe", launcher.LOCALE_EMULATOR, r"C:\LE\LEProc.exe") == [
        r"C:\LE\LEProc.exe", r"C:\vn\game.exe"]
    assert launcher.command(r"C:\vn\game.exe", launcher.NTLEA, r"C:\ntlea\ntleas.exe") == [
        r"C:\ntlea\ntleas.exe", r"C:\vn\game.exe", "C932", "L1041"]


def test_launch_errors(cfg, tmp_path):
    with pytest.raises(FileNotFoundError):
        launcher.launch(cfg, {"path": str(tmp_path / "gone.exe")})
    game = tmp_path / "game.exe"
    game.write_bytes(b"")
    with pytest.raises(launcher.ToolMissing) as err:
        launcher.launch(cfg, {"path": str(game), "launcher": "le"})
    assert err.value.launcher == "le"
    cfg["locale_emulator_path"] = str(tmp_path / "moved" / "LEProc.exe")
    with pytest.raises(launcher.ToolMissing):
        launcher.launch(cfg, {"path": str(game), "launcher": "le"})


def test_launch_through_locale_emulator(cfg, tmp_path, monkeypatch):
    game, tool = tmp_path / "vn" / "game.exe", tmp_path / "LE" / "LEProc.exe"
    for f in (game, tool):
        f.parent.mkdir(parents=True)
        f.write_bytes(b"")
    cfg["locale_emulator_path"] = str(tool)
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw["cwd"])))
    launcher.launch(cfg, {"path": str(game), "launcher": "le"})
    assert calls == [([str(tool), str(game)], str(game.parent))]

    opened = []
    monkeypatch.setattr(launcher.os, "startfile", lambda path, cwd=None: opened.append(path), raising=False)
    launcher.launch(cfg, {"path": str(game), "launcher": "bogus"})  # unknown value: plain launch
    assert opened == [str(game)]
