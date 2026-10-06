"""What the "What's new" page shows: the GitHub release notes of the versions a
user just updated through, trimmed to what still matters once it's installed,
and their Markdown cut into lines the page can style."""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .updater import _HEADERS, REPO, is_newer, parse_version

RELEASES_PAGE = f"https://github.com/{REPO}/releases"
_API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
# Sections that are about getting the update, pointless once it's installed.
_SKIPPED_SECTIONS = {"updating", "update", "install", "installing", "how to update"}


@dataclass
class Notes:
    version: str
    date: str  # "2026-10-04"
    body: str


@dataclass
class Line:
    kind: str  # "h1", "h2", "h3", "bullet", "text" or "blank"
    parts: list[tuple[str, bool]]  # (text, bold)
    level: int = 0  # bullets: how deep


def fetch(session: requests.Session | None = None) -> list[Notes]:
    """Every published release, newest first. Raises on network errors."""
    resp = (session or requests).get(_API, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    out = []
    for rel in resp.json():
        if rel.get("draft") or rel.get("prerelease") or not parse_version(rel.get("tag_name", "")):
            continue
        out.append(Notes(version=rel["tag_name"].lstrip("vV"), date=(rel.get("published_at") or "")[:10],
                         body=clean(rel.get("body") or "", rel["tag_name"])))
    out.sort(key=lambda n: parse_version(n.version), reverse=True)
    return out


def pick(notes: list[Notes], current: str, since: str | None = None, recent: int = 0) -> list[Notes]:
    """The releases to show, newest first: those after ``since`` up to ``current``
    (just ``current`` when ``since`` is None), or the last ``recent`` ones."""
    upto = [n for n in notes if not is_newer(n.version, current)]
    if recent:
        return upto[:recent]
    if since is None:
        return [n for n in upto if not is_newer(current, n.version)][:1]
    return [n for n in upto if is_newer(n.version, since)]


def clean(body: str, tag: str = "") -> str:
    """``body`` without its "Updating" section(s), nor a first heading that only
    repeats the version (the page already says which version it is)."""
    lines = body.replace("\r\n", "\n").split("\n")
    version = tag.lstrip("vV")
    out: list[str] = []
    skip_level = 0  # inside a skipped section of this heading level
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if skip_level and level > skip_level:
                continue
            skip_level = 0
            if title.lower().rstrip(":") in _SKIPPED_SECTIONS:
                skip_level = level
                continue
            if not any(l.strip() for l in out) and version and version in title:
                continue
        elif skip_level:
            continue
        out.append(line)
    return "\n".join(out).strip()


def parse(body: str) -> list[Line]:
    """Markdown (as written for the GitHub releases) -> styled lines: headings,
    bullet points (nested by indentation), paragraphs; **bold** kept, links and
    `code` reduced to their text."""
    out: list[Line] = []
    for raw in body.replace("\r\n", "\n").split("\n"):
        if not raw.strip():
            if out and out[-1].kind != "blank":
                out.append(Line("blank", []))
            continue
        heading = re.match(r"^\s*(#{1,6})\s+(.*)$", raw)
        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", raw)
        if heading:
            out.append(Line(f"h{min(3, len(heading.group(1)))}", _inline(heading.group(2))))
        elif bullet:
            out.append(Line("bullet", _inline(bullet.group(2)), level=len(bullet.group(1).expandtabs(4)) // 2))
        else:
            out.append(Line("text", _inline(raw.strip())))
    while out and out[-1].kind == "blank":
        out.pop()
    return out


def _inline(text: str) -> list[tuple[str, bool]]:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"`([^`]*)`", r"\1", text)
    parts = []
    for i, piece in enumerate(re.split(r"\*\*|__", text)):
        if piece:
            parts.append((piece, i % 2 == 1))
    return parts
