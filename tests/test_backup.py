import zipfile

import pytest

from vnrpc import backup
from vnrpc import config as config_mod
from vnrpc.config import Config


@pytest.fixture
def pc(tmp_path, monkeypatch):
    """Point the app's data folder at ``tmp_path/<name>``, like a fresh PC."""
    def use(name: str) -> Config:
        root = tmp_path / name
        monkeypatch.setattr(config_mod, "GAMES_DIR", root / "games")
        monkeypatch.setattr(config_mod, "CONFIG_FILE", root / "config.yaml")
        monkeypatch.setattr(config_mod, "SETTINGS_FILE", root / "settings.json")
        monkeypatch.setattr(backup, "LOCAL_COVER_DIR", root / "covers")
        monkeypatch.setattr(backup, "BACKUP_DIR", root / "backups")
        return Config.load()
    return use


def test_export_then_import_on_another_pc(pc, tmp_path):
    old = pc("old")
    cover = tmp_path / "old" / "covers" / "abc.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"png")
    old["theme"] = "light"
    old.save()
    old.set_game_override("cmvs64", name="Hapymaher", status="playing", path=r"D:\VN\Hapymaher\cmvs64.exe",
                          cover_source="local", cover_value=str(cover))
    old.add_playtime_seconds("cmvs64", 3600)
    old.set_game_override("siglus", name="Clannad")
    file = tmp_path / "backup.zip"
    assert backup.export_data(old, file) == 2

    new = pc("new")
    new.set_game_override("leftover", name="Only on the new PC")
    assert backup.import_data(new, file) == 2

    assert new["theme"] == "light"
    assert set(new.all_games()) == {"cmvs64", "siglus"}
    assert new.get_playtime_seconds("cmvs64") == 3600
    entry = new.game_override("cmvs64")
    assert entry["name"] == "Hapymaher"
    moved = tmp_path / "new" / "covers" / "0001_abc.png"
    assert entry["cover_value"] == str(moved) and moved.read_bytes() == b"png"

    # what was there before is kept aside, and the files on disk match what's loaded
    assert len(list((tmp_path / "new" / "backups").glob("before-import-*.zip"))) == 1
    assert set(Config.load().all_games()) == {"cmvs64", "siglus"}


def test_rejects_files_that_arent_backups(pc, tmp_path):
    cfg = pc("pc")
    cfg.set_game_override("game", name="Kept")
    junk = tmp_path / "junk.zip"
    with zipfile.ZipFile(junk, "w") as zf:
        zf.writestr("hello.txt", "hi")
    not_zip = tmp_path / "x.zip"
    not_zip.write_text("nope")
    for bad in (junk, not_zip):
        with pytest.raises(backup.BackupError):
            backup.import_data(cfg, bad)
    assert set(cfg.all_games()) == {"game"}


def test_rejects_newer_format(pc, tmp_path):
    cfg = pc("pc")
    file = tmp_path / "b.zip"
    with zipfile.ZipFile(file, "w") as zf:
        zf.writestr("config.yaml", "{}")
        zf.writestr("vnrpc-backup.json", '{"format": 99}')
    with pytest.raises(backup.BackupError, match="newer"):
        backup.import_data(cfg, file)
