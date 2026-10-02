import random

from vnrpc.ui.wishlist_page import length_text, pick_order
from vnrpc.vndb import WISHLIST_LABEL, VNDBClient, VNResult


class _Resp:
    status_code = 200

    def __init__(self, data) -> None:
        self._data = data
        self.content = b"x"

    def json(self):
        return self._data


class _Session:
    """Answers /authinfo, then /ulist one page at a time."""

    def __init__(self, pages) -> None:
        self.headers = {}
        self.pages = pages
        self.bodies = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        if url.endswith("/authinfo"):
            return _Resp({"id": "u1", "username": "len", "permissions": ["listread"]})
        self.bodies.append(json)
        page = json["page"]
        return _Resp({"results": self.pages[page - 1], "more": page < len(self.pages)})


def _entry(vn_id, title, minutes=0):
    return {"id": vn_id, "vn": {"title": title, "released": "2010-01-01", "rating": 80,
                                "image": {"url": f"https://img/{vn_id}.jpg"}, "length_minutes": minutes}}


def test_get_wishlist_reads_every_page(monkeypatch):
    monkeypatch.setattr("vnrpc.vndb._MIN_INTERVAL", 0)
    session = _Session([[_entry("v1", "One", 600), _entry("v2", "Two")], [_entry("v3", "Three")]])
    wishlist = VNDBClient(session=session).get_wishlist("token")
    assert [vn.id for vn in wishlist] == ["v1", "v2", "v3"]
    assert wishlist[0].title == "One" and wishlist[0].year == "2010"
    assert wishlist[0]._extra["length_minutes"] == 600
    assert session.bodies[0]["user"] == "u1"
    assert session.bodies[0]["filters"] == ["label", "=", WISHLIST_LABEL]
    assert [b["page"] for b in session.bodies] == [1, 2]


def test_pick_order_skips_the_library_unless_nothing_is_left():
    wishlist = [VNResult(id=f"v{n}", title=str(n)) for n in range(5)]
    order = pick_order(wishlist, {"v0", "v1"}, random.Random(1))
    assert sorted(vn.id for vn in order) == ["v2", "v3", "v4"]
    order = pick_order(wishlist, {vn.id for vn in wishlist}, random.Random(1))
    assert len(order) == 5


def test_length_text():
    assert length_text(0) == ""
    assert length_text(45) == "~45m"
    assert length_text(90) == "~1.5h"
    assert length_text(3750) == "~62h"
