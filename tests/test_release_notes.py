from vnrpc import release_notes as rn
from vnrpc.release_notes import Notes

BODY = """## Visual Novel RPC v1.2.4

## New

- **Desktop mascot** (ukagaka style): a character on your desktop.
  - Drag her anywhere. See [the README](https://github.com/x/y).
- Uses `assets/mascot.png`.

## Updating

- **From 1.2.1 or newer**: the app offers this update by itself.
  - nested detail

## Changed

- Rating reads "Rating 7.4".
"""


def test_clean_drops_the_updating_section_and_the_version_title():
    text = rn.clean(BODY, "v1.2.4")
    assert "Updating" not in text and "offers this update" not in text and "nested detail" not in text
    assert "Visual Novel RPC v1.2.4" not in text
    assert text.startswith("## New") and "## Changed" in text and "Rating 7.4" in text


def test_parse_markdown():
    lines = [line for line in rn.parse(rn.clean(BODY, "v1.2.4")) if line.kind != "blank"]
    kinds = [(line.kind, line.level) for line in lines]
    assert kinds == [("h2", 0), ("bullet", 0), ("bullet", 1), ("bullet", 0), ("h2", 0), ("bullet", 0)]
    first = lines[1]
    assert first.parts[0] == ("Desktop mascot", True)
    assert first.parts[1][1] is False and "ukagaka" in first.parts[1][0]
    nested = lines[2]
    assert "".join(p for p, _ in nested.parts) == "Drag her anywhere. See the README."
    assert "".join(p for p, _ in lines[3].parts) == "Uses assets/mascot.png."


def test_pick_the_versions_to_show():
    notes = [Notes(v, "", "") for v in ("1.3.0", "1.2.6", "1.2.5", "1.2.4", "1.2.0")]
    versions = lambda picked: [n.version for n in picked]  # noqa: E731
    assert versions(rn.pick(notes, "1.2.6", since="1.2.4")) == ["1.2.6", "1.2.5"]  # skipped 1.2.5
    assert versions(rn.pick(notes, "1.2.6")) == ["1.2.6"]  # never a newer one than installed
    assert versions(rn.pick(notes, "1.2.6", recent=3)) == ["1.2.6", "1.2.5", "1.2.4"]
    assert versions(rn.pick(notes, "1.2.7")) == []  # no notes for this version: nothing, not an older one's
