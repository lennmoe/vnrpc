import pytest

from vnrpc import config as config_mod
from vnrpc.config import Config
from vnrpc.core import VNRPCEngine
from vnrpc.ui.game_page import NO_VOTE, vote_label, vote_value
from vnrpc.vndb import VNDBError


class FakeVNDB:
    def __init__(self, vote=None):
        self.entry = {"vote": vote} if vote else None
        self.patches = []

    def get_list_entry(self, token, vn_id):
        return self.entry

    def update_list_entry(self, token, vn_id, changes):
        self.patches.append((token, vn_id, changes))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    cfg = Config()
    cfg["vndb_token"] = "tok"
    cfg.set_game_override("hapy", vndb_id="v10957")
    eng = VNRPCEngine(cfg)
    eng.vndb = FakeVNDB(vote=85)
    return eng


def test_vote_labels():
    assert vote_label(85) == "8.5"
    assert vote_label(100) == "10"
    assert vote_label(83) == "8.3"
    assert vote_label(None) == vote_label(0) == NO_VOTE
    assert vote_value("8.5") == 85
    assert vote_value("10") == 100
    assert vote_value(NO_VOTE) is None


def test_read_and_remember_the_vote(engine):
    assert engine.vndb_vote("hapy") == 85
    assert engine.config.game_override("hapy")["vndb_vote"] == 85


def test_set_and_remove_the_vote(engine):
    engine.set_vndb_vote("hapy", 90)
    engine.set_vndb_vote("hapy", None)
    assert engine.vndb.patches == [("tok", "v10957", {"vote": 90}), ("tok", "v10957", {"vote": None})]
    assert engine.config.game_override("hapy")["vndb_vote"] == 0


def test_vote_needs_a_token_and_a_confirmed_vn(engine):
    engine.config["vndb_token"] = ""
    with pytest.raises(VNDBError, match="token"):
        engine.set_vndb_vote("hapy", 90)
    engine.config["vndb_token"] = "tok"
    engine.config.set_game_override("other", matched_vndb_id="v1")  # found automatically, not confirmed
    with pytest.raises(VNDBError, match="confirm"):
        engine.vndb_vote("other")
    with pytest.raises(ValueError):
        engine.set_vndb_vote("hapy", 5)
    assert engine.vndb.patches == []
