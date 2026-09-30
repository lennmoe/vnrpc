from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .paths import COVER_CACHE_DIR, VNDB_CACHE_DIR, ensure_dirs

API_BASE = "https://api.vndb.org/kana"
USER_AGENT = "VisualNovelRPC/1.0 (+https://github.com/; local desktop app)"
_MIN_INTERVAL = 1.1

# Pre-defined VNDB list labels; the website keeps these four mutually exclusive.
LIST_LABELS = {"playing": 1, "finished": 2, "stalled": 3, "dropped": 4}

_QUERY_FIELDS = (
    "id,title,alttitle,released,rating,"
    "image.url,image.dims,image.sexual,image.violence"
)


@dataclass
class VNResult:
    id: str
    title: str
    alt_title: str = ""
    year: str = ""
    image_url: str = ""
    sexual: float = 0.0
    violence: float = 0.0
    rating: float = 0.0
    _extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_nsfw(self) -> bool:
        return self.sexual >= 1.0 or self.violence >= 1.0

    @property
    def vndb_url(self) -> str:
        return f"https://vndb.org/{self.id}"

    @classmethod
    def from_api(cls, obj: dict[str, Any]) -> "VNResult":
        img = obj.get("image") or {}
        released = obj.get("released") or ""
        return cls(
            id=obj.get("id", ""),
            title=obj.get("title", "") or "",
            alt_title=obj.get("alttitle") or "",
            year=released[:4] if released else "",
            image_url=img.get("url", "") or "",
            sexual=float(img.get("sexual") or 0),
            violence=float(img.get("violence") or 0),
            rating=float(obj.get("rating") or 0),
        )


@dataclass
class ReleaseCover:
    """One box-art image from one of a VN's releases (front/back/side/etc.)."""
    url: str
    type: str
    release_id: str
    release_title: str
    sexual: float = 0.0
    violence: float = 0.0

    @property
    def is_nsfw(self) -> bool:
        return self.sexual >= 1.0 or self.violence >= 1.0


class VNDBError(RuntimeError):
    pass


class VNDBClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        ensure_dirs()
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._auth_cache: dict[str, dict[str, Any]] = {}

    def _throttle(self) -> None:
        with self._lock:
            wait = _MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", endpoint, body)

    def _request(
        self, method: str, endpoint: str, body: dict[str, Any] | None = None, token: str = ""
    ) -> dict[str, Any]:
        url = f"{API_BASE}{endpoint}"
        headers = {"Authorization": f"Token {token}"} if token else {}
        for attempt in range(4):
            self._throttle()
            try:
                resp = self._session.request(method, url, json=body, headers=headers, timeout=15)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise VNDBError(f"network error: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code == 401:
                raise VNDBError("the VNDB token is invalid or was revoked")
            if resp.status_code >= 400:
                raise VNDBError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json() if resp.content else {}
        raise VNDBError("rate limited, giving up")

    def list_user(self, token: str) -> dict[str, Any]:
        """``{"id", "username", "permissions"}`` for a token that may edit its owner's list."""
        if token not in self._auth_cache:
            info = self._request("GET", "/authinfo", token=token)
            if "listwrite" not in (info.get("permissions") or []):
                raise VNDBError("this token can't edit your list (it needs list write access)")
            self._auth_cache[token] = info
        return self._auth_cache[token]

    def get_list_entry(self, token: str, vn_id: str) -> dict[str, Any] | None:
        """The user's list entry for ``vn_id`` (labels, started, finished, vote), if any."""
        body = {
            "user": self.list_user(token)["id"],
            "filters": ["id", "=", vn_id],
            "fields": "labels.id,started,finished,vote",
        }
        results = self._request("POST", "/ulist", body, token=token).get("results") or []
        return results[0] if results else None

    def update_list_entry(self, token: str, vn_id: str, changes: dict[str, Any]) -> None:
        """PATCH the user's list entry (VNDB adds the VN to the list if it isn't there yet)."""
        self._request("PATCH", f"/ulist/{vn_id}", changes, token=token)

    def search_vn(self, query: str, limit: int = 10, use_cache: bool = True) -> list[VNResult]:
        query = (query or "").strip()
        if not query:
            return []
        cache_file = VNDB_CACHE_DIR / f"{_hash(query.lower())}.json"
        if use_cache and cache_file.exists() and _fresh(cache_file, days=7):
            try:
                raw = json.loads(cache_file.read_text("utf-8"))
                return [VNResult.from_api(o) for o in raw]
            except (OSError, json.JSONDecodeError):
                pass

        body = {
            "filters": ["search", "=", query],
            "fields": _QUERY_FIELDS,
            "results": max(1, min(limit, 25)),
            "sort": "searchrank",
        }
        data = self._post("/vn", body)
        results = data.get("results", []) or []
        try:
            cache_file.write_text(json.dumps(results, ensure_ascii=False), "utf-8")
        except OSError:
            pass
        return [VNResult.from_api(o) for o in results]

    def get_release_covers(self, vn_id: str, use_cache: bool = True) -> list[ReleaseCover]:
        """Every box-art image across all of a VN's releases (different editions
        often ship different cover art than the default one VNDB picks)."""
        vn_id = (vn_id or "").strip()
        if not vn_id:
            return []
        if not vn_id.startswith("v"):
            vn_id = "v" + vn_id
        cache_file = VNDB_CACHE_DIR / f"releases_{vn_id}.json"
        if use_cache and cache_file.exists() and _fresh(cache_file, days=7):
            try:
                raw = json.loads(cache_file.read_text("utf-8"))
                covers: list[ReleaseCover] = []
                for o in raw:
                    covers.extend(_release_covers_from_api(o))
                return covers
            except (OSError, json.JSONDecodeError):
                pass

        body = {
            "filters": ["vn", "=", ["id", "=", vn_id]],
            "fields": "id,title,released,images.url,images.type,images.sexual,images.violence",
            "results": 100,
            "sort": "released",
        }
        data = self._post("/release", body)
        results = data.get("results", []) or []
        try:
            cache_file.write_text(json.dumps(results, ensure_ascii=False), "utf-8")
        except OSError:
            pass
        covers = []
        for o in results:
            covers.extend(_release_covers_from_api(o))
        return covers

    def get_vn(self, vn_id: str) -> VNResult | None:
        vn_id = vn_id.strip()
        if not vn_id.startswith("v"):
            vn_id = "v" + vn_id
        body = {"filters": ["id", "=", vn_id], "fields": _QUERY_FIELDS, "results": 1}
        data = self._post("/vn", body)
        results = data.get("results", []) or []
        return VNResult.from_api(results[0]) if results else None

    def cover_path(self, vn_id: str, image_url: str) -> str | None:
        """Download a cover to the on-disk cache and return the local path."""
        if not image_url:
            return None
        ext = ".jpg"
        if "." in image_url.rsplit("/", 1)[-1]:
            ext = "." + image_url.rsplit(".", 1)[-1].split("?")[0][:4]
        dest = COVER_CACHE_DIR / f"{vn_id or _hash(image_url)}{ext}"
        if dest.exists() and dest.stat().st_size > 0:
            return str(dest)
        try:
            self._throttle()
            resp = self._session.get(image_url, timeout=20)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return str(dest)
        except (requests.RequestException, OSError):
            return None


def push_list_status(
    client: VNDBClient, token: str, vn_id: str, status: str, *, keep_existing: bool = False
) -> str:
    """Put ``vn_id`` on the user's VNDB list as ``status`` (a :data:`LIST_LABELS` key,
    or ``""`` to take those labels off) and return the status it ends up with.
    ``keep_existing``: if it's already on the list as Playing/Finished/Stalled/Dropped,
    leave it alone and return that instead."""
    entry = client.get_list_entry(token, vn_id) or {}
    label_ids = {lbl.get("id") for lbl in entry.get("labels") or []}
    current = next((name for name, lid in LIST_LABELS.items() if lid in label_ids), "")
    if current == status or (current and keep_existing):
        return current
    if not status:
        client.update_list_entry(token, vn_id, {"labels_unset": list(LIST_LABELS.values())})
        return ""
    changes: dict[str, Any] = {
        "labels_set": [LIST_LABELS[status]],
        "labels_unset": [lid for name, lid in LIST_LABELS.items() if name != status],
    }
    today = time.strftime("%Y-%m-%d")
    if not entry.get("started"):
        changes["started"] = today
    if status == "finished" and not entry.get("finished"):
        changes["finished"] = today
    client.update_list_entry(token, vn_id, changes)
    return status


def _release_covers_from_api(obj: dict[str, Any]) -> list[ReleaseCover]:
    out: list[ReleaseCover] = []
    for img in obj.get("images") or []:
        url = img.get("url") or ""
        if not url:
            continue
        out.append(
            ReleaseCover(
                url=url,
                type=img.get("type") or "",
                release_id=obj.get("id", ""),
                release_title=obj.get("title", "") or "",
                sexual=float(img.get("sexual") or 0),
                violence=float(img.get("violence") or 0),
            )
        )
    return out


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _fresh(path, days: int) -> bool:
    return (time.time() - path.stat().st_mtime) < days * 86400
