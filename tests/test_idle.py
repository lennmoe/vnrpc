import pytest

from vnrpc import config as config_mod
from vnrpc import core
from vnrpc.config import Config
from vnrpc.core import Snapshot, VNRPCEngine

T0 = 1_000_000.0
VN_HWND, VN_PID = 111, 42
OTHER_HWND = 222


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    c = Config()
    c["idle_when_unfocused"] = True
    c["idle_seconds"] = 60
    return c


@pytest.fixture
def world(cfg, monkeypatch):
    """An engine reading "game" since T0, with a fake clock and foreground window."""
    state = {"now": T0, "fg": VN_HWND}
    monkeypatch.setattr(core.time, "time", lambda: state["now"])
    monkeypatch.setattr(core, "foreground_window", lambda: state["fg"])
    monkeypatch.setattr(core, "window_pid", lambda hwnd: VN_PID if hwnd == VN_HWND else 7)
    engine = VNRPCEngine(cfg)
    pushed = []
    engine.presence.set_activity = pushed.append
    engine._playtime_key = "game"
    engine._playtime_tick_start = T0
    engine._session_start = int(T0)
    engine._snapshot = Snapshot(detected=True, key="game", game_name="VN", hwnd=VN_HWND, pid=VN_PID,
                                session_start=int(T0))

    def at(seconds: float, fg: int) -> None:
        state["now"], state["fg"] = T0 + seconds, fg
        engine._check_idle()

    return engine, at, pushed


def test_goes_idle_after_the_delay_and_stops_counting(world, cfg):
    engine, at, pushed = world
    at(100, OTHER_HWND)  # loses the focus at +100s
    at(130, OTHER_HWND)
    assert not engine.snapshot.idle
    at(160, OTHER_HWND)
    assert engine.snapshot.idle
    assert pushed[-1] is None  # Discord cleared
    assert cfg.get_playtime_seconds("game") == 100  # only up to when it lost the focus

    engine._flush_playtime()
    at(1000, OTHER_HWND)
    assert cfg.get_playtime_seconds("game") == 100


def test_coming_back_resumes_the_timers_where_they_stopped(world, cfg):
    engine, at, pushed = world
    at(100, OTHER_HWND)
    at(200, OTHER_HWND)
    at(700, VN_HWND)  # away for 600s
    snap = engine.snapshot
    assert not snap.idle
    assert snap.session_start == int(T0) + 600  # Discord's elapsed time skips the idle part
    assert pushed[-1] is not None and pushed[-1].start == int(T0) + 600
    at(760, VN_HWND)
    engine._flush_playtime()
    assert cfg.get_playtime_seconds("game") == 160  # 100 before + 60 after


def test_short_alt_tab_still_counts(world, cfg):
    engine, at, _ = world
    at(100, OTHER_HWND)
    at(130, VN_HWND)  # back after 30s, under the delay
    assert not engine.snapshot.idle
    at(200, VN_HWND)
    engine._flush_playtime()
    assert cfg.get_playtime_seconds("game") == 200


def test_another_window_of_the_game_counts_as_focused(world, monkeypatch):
    engine, at, _ = world
    monkeypatch.setattr(core, "window_pid", lambda hwnd: VN_PID)  # e.g. its config dialog
    at(100, OTHER_HWND)
    at(500, OTHER_HWND)
    assert not engine.snapshot.idle


def test_turned_off_never_goes_idle(world, cfg):
    engine, at, _ = world
    cfg["idle_when_unfocused"] = False
    at(100, OTHER_HWND)
    at(500, OTHER_HWND)
    assert not engine.snapshot.idle


def test_activity_is_none_while_idle(cfg):
    engine = VNRPCEngine(cfg)
    assert engine.activity_for(Snapshot(detected=True, game_name="VN", idle=True)) is None
