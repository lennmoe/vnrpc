from __future__ import annotations

import hashlib

import pytest

from vnrpc import updater


class _Resp:
    def __init__(self, data) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._data


class _Session:
    def __init__(self, data) -> None:
        self.data = data

    def get(self, *_a, **_kw):
        return _Resp(self.data)


def _release(tag="v1.2.1", assets=None, **extra):
    return {
        "tag_name": tag, "draft": False, "prerelease": False, "body": "Fixes",
        "html_url": "https://github.com/x/y/releases/tag/" + tag,
        "assets": assets if assets is not None else [{
            "name": "VisualNovelRPC.exe", "size": 3, "digest": "sha256:ABC",
            "browser_download_url": "https://example.com/VisualNovelRPC.exe",
        }],
        **extra,
    }


@pytest.mark.parametrize("tag,current,newer", [
    ("v1.2.1", "1.2.0", True),
    ("1.2.1", "1.2.1", False),
    ("v1.10.0", "1.9.3", True),
    ("v1.2", "1.2.0", False),
    ("1.2.0.1", "1.2", True),
    ("v1.1.0", "1.2.0", False),
    ("vn", "1.2.0", False),
])
def test_is_newer(tag, current, newer):
    assert updater.is_newer(tag, current) is newer


def test_find_update_returns_exe_asset():
    rel = updater.find_update("1.2.0", session=_Session(_release()))
    assert rel is not None
    assert rel.version == "1.2.1"
    assert rel.url.endswith("VisualNovelRPC.exe")
    assert rel.sha256 == "abc"
    assert rel.size == 3


def test_find_update_skips_same_version_prerelease_and_missing_exe():
    assert updater.find_update("1.2.1", session=_Session(_release())) is None
    assert updater.find_update("1.2.0", session=_Session(_release(prerelease=True))) is None
    assert updater.find_update("1.2.0", session=_Session(_release(assets=[]))) is None


def test_download_rejects_bad_hash(tmp_path, monkeypatch):
    payload = b"exe"

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, _n):
            yield payload

    monkeypatch.setattr(updater.requests, "get", lambda *_a, **_kw: _Stream())
    good = updater.Release("1.2.1", "u", 3, hashlib.sha256(payload).hexdigest(), "", "")
    assert updater.download(good, tmp_path / "new.exe").read_bytes() == payload

    bad = updater.Release("1.2.1", "u", 3, "0" * 64, "", "")
    with pytest.raises(OSError):
        updater.download(bad, tmp_path / "other.exe")
    assert not (tmp_path / "other.exe").exists()
    assert not (tmp_path / "other.exe.part").exists()
