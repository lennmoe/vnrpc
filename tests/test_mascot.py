from PIL import Image

from vnrpc.ui import mascot


def test_load_character_crops_and_scales(tmp_path):
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (100, 50, 200, 250))  # a 100x200 opaque figure
    path = tmp_path / "char.png"
    img.save(path)
    out = mascot.load_character(str(path), 400)
    assert out.size == (200, 400)


def test_load_character_falls_back_to_the_built_in_one(tmp_path):
    out = mascot.load_character(str(tmp_path / "missing.png"), 300)
    assert out.height == 300 and out.mode == "RGBA"
    assert mascot.load_character("", 300).size == out.size


def test_premultiplied_bgra():
    img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    b, g, r, a = mascot.premultiplied_bgra(img)
    assert a == 128
    assert (r, g, b) == (round(200 * 128 / 255), round(100 * 128 / 255), round(50 * 128 / 255))


def test_clamp_position_rejects_off_screen(monkeypatch):
    metrics = {mascot.SM_XVIRTUALSCREEN: 0, mascot.SM_YVIRTUALSCREEN: 0,
               mascot.SM_CXVIRTUALSCREEN: 1920, mascot.SM_CYVIRTUALSCREEN: 1080}
    monkeypatch.setattr(mascot.user32, "GetSystemMetrics", lambda i: metrics[i])
    assert mascot.clamp_position([1500, 600], (200, 400)) == (1500, 600)
    assert mascot.clamp_position([5000, 600], (200, 400)) is None  # a screen that's gone
    assert mascot.clamp_position(None, (200, 400)) is None
