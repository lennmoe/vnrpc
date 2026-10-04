from vnrpc.ui import theme


def test_every_theme_defines_every_color():
    keys = [set(palette) for palette in theme.THEMES.values()]
    assert all(k == keys[0] for k in keys)
    for palette in theme.THEMES.values():
        assert palette["mode"] in ("light", "dark")
        assert all(v.startswith("#") and len(v) == 7 for k, v in palette.items() if k.isupper())


def test_apply_theme_updates_tokens_and_falls_back_to_dark():
    try:
        theme.apply_theme("sakura")
        assert theme.BG == "#FFDCE8" and theme.STATUS_COLORS["playing"] == theme.ACCENT
        theme.apply_theme("no-such-theme")
        assert theme.current_theme == "dark" and theme.BG == theme.THEMES["dark"]["BG"]
    finally:
        theme.apply_theme("dark")


def test_normalize_hex():
    assert theme.normalize_hex("fdc") == "#FFDDCC"
    assert theme.normalize_hex(" #ffdce8 ") == "#FFDCE8"
    assert theme.normalize_hex("FBE3EB") == "#FBE3EB"
    for bad in ("", None, "#12345", "#GGGGGG", "pink"):
        assert theme.normalize_hex(bad) is None


def test_custom_palette_is_derived_from_four_colors():
    p = theme.build_custom_palette({
        "mode": "light", "BG": "#FFDCE8", "SURFACE": "#FBE3EB", "ACCENT": "#2A9D8F", "TEXT": "#3A2230",
        "overrides": {"GREEN": "#0b6e3a", "NOT_A_TOKEN": "#FFFFFF", "RED": "nope"},
    })
    assert p["mode"] == "light" and p["BG"] == "#FFDCE8" and p["ACCENT"] == "#2A9D8F"
    assert set(theme.TOKENS) <= set(p)
    assert p["GREEN"] == "#0B6E3A" and p["RED"] == theme.THEMES["light"]["RED"]
    assert "NOT_A_TOKEN" not in p
    # What sits on the accent, and the selected segment's text, stay readable.
    assert theme.contrast(p["ON_ACCENT"], p["ACCENT"]) >= 3
    assert theme.contrast(p["TEXT"], p["SELECTED"]) >= 4.5


def test_bad_custom_colors_fall_back_to_the_base_theme():
    p = theme.build_custom_palette({"mode": "dark", "BG": "oops", "ACCENT": "#123"})
    assert p["BG"] == theme.THEMES["dark"]["BG"]
    assert p["ACCENT"] == "#112233"


def test_every_theme_is_readable():
    for name, p in theme.THEMES.items():
        if name == "custom":
            continue
        assert theme.contrast(p["TEXT"], p["SURFACE"]) >= 7, name
        assert theme.contrast(p["MUTED"], p["SURFACE"]) >= 4.5, name
        assert theme.contrast(p["ACCENT"], p["SURFACE"]) >= 3, name  # chart bars, accent labels
        assert theme.contrast(p["ON_ACCENT"], p["ACCENT"]) >= 4.3, name  # button text
        assert theme.contrast(p["TEXT"], p["SELECTED"]) >= 4.5 or name == "dark", name


def test_system_theme_follows_windows(monkeypatch):
    try:
        monkeypatch.setattr(theme, "windows_mode", lambda: "light")
        theme.apply_theme("system")
        assert theme.current_theme == "system" and theme.resolved_theme == "light"
        assert theme.BG == theme.THEMES["light"]["BG"]
        monkeypatch.setattr(theme, "windows_mode", lambda: "dark")
        theme.apply_theme("system")
        assert theme.BG == theme.THEMES["dark"]["BG"]
    finally:
        theme.apply_theme("dark")


def test_custom_is_the_last_theme():
    names = list(theme.THEMES)
    assert names[-1] == "custom"
    assert {"dark", "light", "sakura", "dracula", "nord", "mocha", "latte", "solarized"} <= set(names)


def test_theme_tile_image():
    from vnrpc.ui.theme_editor import TILE_H, TILE_W, _SCALE, tile_image

    img = tile_image((theme.THEMES["dark"], theme.THEMES["light"]), "Match Windows", ring="#5865F2",
                     bold=True, label_color="#FFFFFF")
    assert img.mode == "RGBA" and img.size == (TILE_W * _SCALE, TILE_H * _SCALE)
    assert img.getpixel((0, 0))[3] == 0  # rounded corner: see-through
    left, right = img.getpixel((4 * _SCALE, 50 * _SCALE)), img.getpixel((img.width - 5 * _SCALE, 50 * _SCALE))
    assert left[:3] != right[:3]  # dark half, light half
