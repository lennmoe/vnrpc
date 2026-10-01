import pytest

from vnrpc import hotkey
from vnrpc.hotkey import WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP

F12, PRINT, S = 0x7B, 0x2C, ord("S")


@pytest.fixture
def listener(monkeypatch):
    """A listener armed for ``combo`` with the game in front and ``mods`` held."""
    state = {"mods": 0, "front": True}
    monkeypatch.setattr(hotkey, "_held_modifiers", lambda: state["mods"])
    presses = []
    lst = hotkey.HotkeyListener(on_press=lambda: presses.append(1))
    monkeypatch.setattr(lst, "_game_in_front", lambda: state["front"])

    def arm(text: str):
        lst._combo = hotkey.parse(text)
        return lst, presses, state

    return arm


def test_f12_alone_works(listener):
    lst, presses, _ = listener("F12")
    assert lst.handle_key(WM_KEYDOWN, F12) is True  # kept from the game
    assert lst.handle_key(WM_KEYDOWN, F12) is True  # auto-repeat: no second shot
    assert lst.handle_key(WM_KEYUP, F12) is True
    assert presses == [1]
    lst.handle_key(WM_KEYDOWN, F12)
    assert presses == [1, 1]


def test_other_keys_and_other_modifiers_pass_through(listener):
    lst, presses, state = listener("Ctrl+S")
    assert lst.handle_key(WM_KEYDOWN, S) is False  # S without Ctrl is just typing
    state["mods"] = hotkey.MOD_CONTROL | hotkey.MOD_SHIFT
    assert lst.handle_key(WM_KEYDOWN, S) is False  # Ctrl+Shift+S is another combination
    state["mods"] = hotkey.MOD_CONTROL
    assert lst.handle_key(WM_KEYDOWN, ord("A")) is False
    assert lst.handle_key(WM_KEYDOWN, S) is True
    assert presses == [1]


def test_alt_combinations_come_as_syskeys(listener):
    lst, presses, state = listener("Alt+F11")
    state["mods"] = hotkey.MOD_ALT
    assert lst.handle_key(WM_SYSKEYDOWN, 0x7A) is True
    assert lst.handle_key(WM_SYSKEYUP, 0x7A) is True
    assert presses == [1]


def test_nothing_when_the_game_isnt_in_front(listener):
    lst, presses, state = listener("F12")
    state["front"] = False
    assert lst.handle_key(WM_KEYDOWN, F12) is False
    assert lst.handle_key(WM_KEYUP, F12) is False
    assert presses == []


def test_print_screen_reported_only_on_release(listener):
    lst, presses, _ = listener("PrintScreen")
    assert lst.handle_key(WM_KEYUP, PRINT) is True
    assert presses == [1]


def test_disarmed_listener_ignores_everything(listener):
    lst, presses, _ = listener("F12")
    lst._combo = None
    assert lst.handle_key(WM_KEYDOWN, F12) is False
    assert presses == []


def test_key_event_falls_back_on_the_virtual_key_code():
    assert hotkey.from_key_event("F12", 0) == "F12"
    assert hotkey.from_key_event("KP_5", 0, 0x65) == "Numpad5"
    assert hotkey.from_key_event("agrave", 0x4, 0x30) == "Ctrl+0"  # AZERTY top-row 0
    assert hotkey.from_key_event("Left", 0) == "Left"
    assert hotkey.from_key_event("Control_L", 0x4, 0x11) is None
    assert hotkey.normalize("numpad5") == "Numpad5"
