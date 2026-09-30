import datetime as dt
import os

import pytest
from PIL import Image

from vnrpc import config as config_mod
from vnrpc import hotkey, screenshots
from vnrpc.config import Config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "GAMES_DIR", tmp_path / "games")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.setattr(screenshots, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    c = Config()
    c["screenshot_dir"] = str(tmp_path / "shots")
    return c


def test_hotkey_parse():
    assert hotkey.parse("PrintScreen") == (0, 0x2C)
    assert hotkey.parse("Ctrl+Shift+S") == (hotkey.MOD_CONTROL | hotkey.MOD_SHIFT, ord("S"))
    assert hotkey.parse("alt+f11") == (hotkey.MOD_ALT, 0x7A)
    assert hotkey.parse("") is None
    assert hotkey.parse("Ctrl+") is None
    assert hotkey.parse("Hyper+S") is None
    assert hotkey.parse("F25") is None


def test_hotkey_normalize():
    assert hotkey.normalize("shift+ctrl+f12") == "Ctrl+Shift+F12"
    assert hotkey.normalize("printscreen") == "PrintScreen"
    assert hotkey.normalize("alt+s") == "Alt+S"
    assert hotkey.normalize("nonsense") == ""
    assert hotkey.normalize(None) == ""


def test_folder_name_is_windows_safe():
    assert screenshots.folder_name('Fate/stay night: "Realta Nua"') == "Fatestay night Realta Nua"
    assert screenshots.folder_name("Sakura...") == "Sakura"
    assert screenshots.folder_name("CON") == "CON_"
    assert screenshots.folder_name("") == "Game"
    assert screenshots.folder_name("恋×シンアイ彼女") == "恋×シンアイ彼女"


def test_folder_name_avoids_taken_names():
    assert screenshots.folder_name("Amatsutsumi", {"amatsutsumi"}) == "Amatsutsumi (2)"
    assert screenshots.folder_name("Amatsutsumi", {"Amatsutsumi", "Amatsutsumi (2)"}) == "Amatsutsumi (3)"


def test_folder_is_named_once_and_kept(cfg, tmp_path):
    cfg.set_game_override("cmvs64", name="Hapymaher")
    assert screenshots.folder_for(cfg, "cmvs64") is None
    folder = screenshots.folder_for(cfg, "cmvs64", create=True)
    assert folder == tmp_path / "shots" / "Hapymaher" and folder.is_dir()
    # Renaming the VN later doesn't move its screenshots.
    cfg.set_game_override("cmvs64", title="Hapymaher -Fragmentation Dream-")
    assert screenshots.folder_for(cfg, "cmvs64") == folder


def test_two_vns_with_the_same_name_get_two_folders(cfg):
    cfg.set_game_override("a", name="Hapymaher")
    cfg.set_game_override("b", name="Hapymaher")
    assert screenshots.folder_for(cfg, "a", create=True).name == "Hapymaher"
    assert screenshots.folder_for(cfg, "b", create=True).name == "Hapymaher (2)"


def test_default_root_is_in_pictures(cfg):
    cfg["screenshot_dir"] = ""
    assert screenshots.root(cfg) == screenshots.default_root()
    assert screenshots.default_root().name == "Visual Novel RPC"


def test_save_keeps_game_and_section(tmp_path):
    when = dt.datetime(2026, 9, 30, 21, 14, 3)
    img = Image.new("RGB", (64, 36), (200, 40, 90))
    path = screenshots.save(img, tmp_path, game="Amatsutsumi", section="Chapter 4", when=when)
    assert path.name == "2026-09-30 21-14-03.png"
    again = screenshots.save(img, tmp_path, when=when)
    assert again.name == "2026-09-30 21-14-03 (2).png"
    assert not list(tmp_path.glob("*.part"))

    info = screenshots.info(path)
    assert (info.width, info.height, info.section, info.taken) == (64, 36, "Chapter 4", when)


def test_list_is_newest_first_and_images_only(tmp_path):
    old = screenshots.save(Image.new("RGB", (4, 4)), tmp_path, when=dt.datetime(2026, 1, 1))
    new = screenshots.save(Image.new("RGB", (4, 4)), tmp_path, when=dt.datetime(2026, 2, 1))
    os.utime(old, (1_000_000, 1_000_000))
    (tmp_path / "notes.txt").write_text("hi")
    assert screenshots.list_shots(tmp_path) == [new, old]
    assert screenshots.list_shots(tmp_path / "missing") == []
    assert screenshots.list_shots(None) == []


def test_thumbnail_is_cached(cfg, tmp_path):
    path = screenshots.save(Image.new("RGB", (1920, 1080), (10, 20, 30)), tmp_path / "vn")
    thumb = screenshots.thumbnail(path, (200, 112))
    assert thumb.size == (200, 112)
    assert len(list((tmp_path / "thumbs").glob("*.jpg"))) == 1
    assert screenshots.thumbnail(path, (200, 112)).size == (200, 112)
    assert len(list((tmp_path / "thumbs").glob("*.jpg"))) == 1
    assert screenshots.thumbnail(tmp_path / "gone.png", (200, 112)) is None


def test_hotkey_hint(cfg):
    cfg["screenshot_hotkey"] = "PrintScreen"
    assert "PrintScreen" in screenshots.hotkey_hint(cfg)
    cfg["screenshot_hotkey"] = ""
    assert "Settings" in screenshots.hotkey_hint(cfg)


def test_hotkey_from_tk_key_event():
    assert hotkey.from_key_event("s", 0x4 | 0x1) == "Ctrl+Shift+S"
    assert hotkey.from_key_event("F11", 0x20000) == "Alt+F11"
    assert hotkey.from_key_event("Print", 0) == "PrintScreen"
    assert hotkey.from_key_event("Prior", 0x4) == "Ctrl+PageUp"
    assert hotkey.from_key_event("Control_L", 0x4) is None
    assert hotkey.from_key_event("s", 0x8) == "S"  # Num Lock on doesn't count


def test_missing_sound_file_stays_silent(tmp_path):
    from vnrpc.sound import Sound

    sound = Sound(tmp_path / "nope.mp3", "vnrpc_test_missing")
    sound.play()
    sound.play()
    sound.close()
