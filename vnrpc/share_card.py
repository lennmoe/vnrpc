"""The "My week / my month in visual novels" image, made to be pasted on Discord."""
from __future__ import annotations

import calendar
import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Mapping

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .core import format_playtime
from .covers import cached_cover_for_entry
from .paths import APP_ICON_PNG

THIS_WEEK, LAST_WEEK, THIS_MONTH, LAST_MONTH = "this_week", "last_week", "this_month", "last_month"
PERIODS = (THIS_WEEK, LAST_WEEK, THIS_MONTH, LAST_MONTH)
PERIOD_LABELS = {THIS_WEEK: "This week", LAST_WEEK: "Last week", THIS_MONTH: "This month",
                 LAST_MONTH: "Last month"}

SIZE = (1280, 720)
_SCALE = 2  # drawn at twice the size, then shrunk: smooth edges and text
_PAD = 56
_COVER = (144, 204)
_COVER_GAP = 20
MAX_COVERS = 5
_CHART_W = 300


@dataclass
class CardVN:
    key: str
    name: str
    seconds: int
    cover: str | None = None
    nsfw: bool = False
    finished: bool = False


@dataclass
class CardData:
    kind: str
    title: str
    subtitle: str
    start: dt.date
    end: dt.date
    total_seconds: int = 0
    days_read: int = 0
    days_so_far: int = 0
    vns: list[CardVN] = field(default_factory=list)  # most read first
    daily: list[tuple[dt.date, int]] = field(default_factory=list)  # every day of the period

    @property
    def finished(self) -> list[CardVN]:
        return [vn for vn in self.vns if vn.finished]


def period(kind: str, today: dt.date) -> tuple[dt.date, dt.date]:
    """First and last day of the period (the last may be in the future)."""
    if kind in (THIS_WEEK, LAST_WEEK):
        monday = today - dt.timedelta(days=today.weekday())
        if kind == LAST_WEEK:
            monday -= dt.timedelta(weeks=1)
        return monday, monday + dt.timedelta(days=6)
    first = today.replace(day=1)
    if kind == LAST_MONTH:
        first = (first - dt.timedelta(days=1)).replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def collect(games: Mapping[str, dict], kind: str, today: dt.date | None = None) -> CardData:
    """What the card shows for ``games`` (Library entries) over period ``kind``."""
    today = today or dt.date.today()
    start, end = period(kind, today)
    last = min(end, today)
    if kind in (THIS_WEEK, LAST_WEEK):
        title = "My week in visual novels"
    else:
        title = f"My {start.strftime('%B')} in visual novels"
    if start.month == end.month:
        subtitle = f"{start.day} – {end.day} {end.strftime('%b %Y')}"
    else:
        subtitle = f"{start.day} {start.strftime('%b')} – {end.day} {end.strftime('%b %Y')}"

    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    per_day = dict.fromkeys(days, 0)
    vns = []
    for key, entry in games.items():
        seconds = 0
        for day_key, secs in (entry.get("daily") or {}).items():
            try:
                day = dt.date.fromisoformat(day_key)
            except (TypeError, ValueError):
                continue
            if start <= day <= last:
                seconds += int(secs)
                per_day[day] += int(secs)
        finished = _finished_between(entry, start, last)
        if seconds > 0 or finished:
            vns.append(CardVN(key, entry.get("title") or entry.get("name") or key, seconds,
                              cached_cover_for_entry(entry), bool(entry.get("cover_nsfw")), finished))
    vns.sort(key=lambda vn: (vn.seconds, vn.finished), reverse=True)
    return CardData(
        kind=kind, title=title, subtitle=subtitle, start=start, end=end,
        total_seconds=sum(per_day.values()),
        days_read=sum(1 for day in days if per_day[day] > 0),
        days_so_far=max(0, (last - start).days + 1),
        vns=vns, daily=sorted(per_day.items()),
    )


def _finished_between(entry: dict, start: dt.date, end: dt.date) -> bool:
    if entry.get("status") != "finished":
        return False
    stamp = entry.get("finished_at") or entry.get("last_played")  # older entries have no finish date
    if not stamp:
        return False
    return start <= dt.date.fromtimestamp(int(stamp)) <= end


_FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_LATIN = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf"}
_CJK = {"regular": "YuGothM.ttc", "semibold": "YuGothB.ttc", "bold": "YuGothB.ttc"}
_CJK_FALLBACK = "meiryo.ttc"
_fonts: dict[tuple, ImageFont.FreeTypeFont] = {}


def _font(size: int, weight: str = "regular", text: str = "") -> ImageFont.FreeTypeFont:
    """Segoe UI, or Yu Gothic for text with Japanese (Segoe has no kana/kanji)."""
    cjk = any(ord(ch) >= 0x2E80 for ch in text)
    key = (size, weight, cjk)
    if key not in _fonts:
        names = [_CJK[weight], _CJK_FALLBACK] if cjk else [_LATIN[weight]]
        font = None
        for name in names:
            try:
                font = ImageFont.truetype(os.path.join(_FONT_DIR, name), size * _SCALE)
                break
            except OSError:
                continue
        _fonts[key] = font or ImageFont.load_default(size * _SCALE)
    return _fonts[key]


class _Canvas:
    """Coordinates in card pixels; drawn at ``_SCALE``x."""

    def __init__(self, bg: str) -> None:
        self.img = Image.new("RGB", (SIZE[0] * _SCALE, SIZE[1] * _SCALE), bg)
        self.draw = ImageDraw.Draw(self.img)

    @staticmethod
    def s(*values: float) -> list[int]:
        return [round(v * _SCALE) for v in values]

    def rect(self, x: float, y: float, w: float, h: float, *, fill=None, outline=None, radius: float = 0,
             width: float = 1) -> None:
        self.draw.rounded_rectangle(self.s(x, y, x + w, y + h), radius=round(radius * _SCALE), fill=fill,
                                    outline=outline, width=round(width * _SCALE))

    def text(self, x: float, y: float, text: str, *, size: int, color: str, weight: str = "regular",
             anchor: str = "la") -> None:
        self.draw.text(self.s(x, y), text, font=_font(size, weight, text), fill=color, anchor=anchor)

    def width(self, text: str, size: int, weight: str = "regular") -> float:
        return _font(size, weight, text).getlength(text) / _SCALE

    def fit(self, text: str, max_w: float, size: int, weight: str = "regular") -> str:
        if self.width(text, size, weight) <= max_w:
            return text
        while text and self.width(text + "…", size, weight) > max_w:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, text: str, max_w: float, size: int, weight: str = "regular", lines: int = 2) -> list[str]:
        """Up to ``lines`` lines, breaking at spaces when there are any (Japanese has none)."""
        out, rest = [], text.strip()
        while rest and len(out) < lines - 1:
            cut = len(rest)
            while cut > 1 and self.width(rest[:cut], size, weight) > max_w:
                cut -= 1
            if cut < len(rest) and " " in rest[:cut + 1]:
                cut = rest[:cut + 1].rindex(" ") or cut
            out.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if rest:
            out.append(self.fit(rest, max_w, size, weight))
        return out

    def paste(self, img: Image.Image, x: float, y: float, radius: float = 0) -> None:
        mask = None
        if radius:
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                                                   radius=round(radius * _SCALE), fill=255)
        self.img.paste(img, tuple(self.s(x, y)), mask)

    def result(self) -> Image.Image:
        return self.img.resize(SIZE, Image.LANCZOS)


def render(data: CardData, palette: Mapping[str, str], *, allow_nsfw: bool = False) -> Image.Image:
    """``palette``: the app theme's colors (BG, SURFACE, SURFACE_ALT, BORDER, TEXT, MUTED,
    SUBTLE, ACCENT, GREEN). NSFW-flagged covers are blurred unless ``allow_nsfw``."""
    p = palette
    c = _Canvas(p["BG"])
    W, H, P = SIZE[0], SIZE[1], _PAD

    # Header
    c.text(P, 44, c.fit(data.title, W - 2 * P - 260, 42, "bold"), size=42, color=p["TEXT"], weight="bold")
    c.text(P, 104, data.subtitle, size=22, color=p["MUTED"])
    brand = "Visual Novel RPC"
    bx = W - P - c.width(brand, 17, "semibold")
    c.text(bx, 66, brand, size=17, color=p["MUTED"], weight="semibold", anchor="lm")
    try:
        with Image.open(APP_ICON_PNG) as icon:
            c.paste(icon.convert("RGB").resize((32 * _SCALE, 32 * _SCALE), Image.LANCZOS), bx - 42, 50, 8)
    except OSError:
        pass

    # Stat tiles
    finished = len(data.finished)
    tiles = (
        ("TIME READ", format_playtime(data.total_seconds), p["TEXT"]),
        ("VISUAL NOVELS", str(len([vn for vn in data.vns if vn.seconds])), p["TEXT"]),
        ("FINISHED", str(finished), p["GREEN"] if finished else p["TEXT"]),
        ("DAYS READ", f"{data.days_read} / {data.days_so_far}", p["TEXT"]),
    )
    gap, top, tile_h = 20, 160, 112
    tile_w = (W - 2 * P - gap * (len(tiles) - 1)) / len(tiles)
    for i, (label, value, color) in enumerate(tiles):
        x = P + i * (tile_w + gap)
        c.rect(x, top, tile_w, tile_h, fill=p["SURFACE"], outline=p["BORDER"], radius=16)
        c.text(x + 24, top + 22, label, size=14, color=p["SUBTLE"], weight="bold")
        c.text(x + 24, top + 46, value, size=38, color=color, weight="bold")

    # Covers of the most read VNs
    top = 304
    shown = data.vns[:MAX_COVERS]
    if not shown:
        left_w = W - 2 * P - _CHART_W - 40
        what = "week" if data.kind in (THIS_WEEK, LAST_WEEK) else "month"
        c.text(P + left_w / 2, top + 150, f"Nothing read this {what}", size=26, color=p["MUTED"],
               weight="semibold", anchor="mm")
    for i, vn in enumerate(shown):
        x = P + i * (_COVER[0] + _COVER_GAP)
        c.paste(_cover_image(vn, p, allow_nsfw), x, top, 12)
        if vn.finished:
            c.rect(x - 2, top - 2, _COVER[0] + 4, _COVER[1] + 4, outline=p["GREEN"], radius=14, width=3)
            c.rect(x + 8, top + 8, c.width("FINISHED", 12, "bold") + 16, 24, fill=p["GREEN"], radius=12)
            c.text(x + 16, top + 20, "FINISHED", size=12, color=p["BG"], weight="bold", anchor="lm")
        y = top + _COVER[1] + 12
        for line in c.wrap(vn.name, _COVER[0], 16, "semibold"):
            c.text(x, y, line, size=16, color=p["TEXT"], weight="semibold")
            y += 22
        if vn.seconds:
            c.text(x, y + 2, format_playtime(vn.seconds), size=15, color=p["MUTED"])

    _draw_chart(c, data, p, W - P - _CHART_W, top, _CHART_W, H - P - top)
    return c.result()


def _cover_image(vn: CardVN, p: Mapping[str, str], allow_nsfw: bool) -> Image.Image:
    w, h = _COVER[0] * _SCALE, _COVER[1] * _SCALE
    img = None
    if vn.cover:
        try:
            with Image.open(vn.cover) as im:
                img = _cover_fit(im.convert("RGB"), (w, h))
        except OSError:
            img = None
    if img is None:
        img = Image.new("RGB", (w, h), p["SURFACE_ALT"])
        initial = (vn.name.strip()[:1] or "?").upper()
        ImageDraw.Draw(img).text((w / 2, h / 2), initial, font=_font(56, "bold", initial), fill=p["SUBTLE"],
                                 anchor="mm")
    elif vn.nsfw and not allow_nsfw:
        img = img.filter(ImageFilter.GaussianBlur(w // 8))
    return img


def _cover_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = max(size[0] / img.width, size[1] / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left, top = (img.width - size[0]) // 2, (img.height - size[1]) // 2
    return img.crop((left, top, left + size[0], top + size[1]))


def _draw_chart(c: _Canvas, data: CardData, p: Mapping[str, str], x: float, y: float, w: float, h: float) -> None:
    c.rect(x, y, w, h, fill=p["SURFACE"], outline=p["BORDER"], radius=16)
    c.text(x + 20, y + 20, "PER DAY", size=14, color=p["SUBTLE"], weight="bold")
    left, right, top, base = x + 20, x + w - 20, y + 64, y + h - 40
    c.draw.line(c.s(left, base, right, base), fill=p["BORDER"], width=_SCALE)
    days = data.daily
    if not days:
        return
    peak = max(secs for _, secs in days)
    slot = (right - left) / len(days)
    bar = max(3.0, min(22.0, slot - 4))
    weekly = len(days) <= 7
    for i, (day, secs) in enumerate(days):
        cx = left + slot * (i + 0.5)
        if weekly or day.day in (1, 8, 15, 22, 29):
            label = "MTWTFSS"[day.weekday()] if weekly else str(day.day)
            c.text(cx, base + 18, label, size=13, color=p["MUTED"], anchor="mm")
        if secs <= 0 or not peak:
            continue
        top_y = base - (base - top) * secs / peak
        c.rect(cx - bar / 2, top_y, bar, base - top_y, fill=p["ACCENT"], radius=min(bar / 2, 5))
        if secs == peak:
            text = format_playtime(secs)
            tx = min(max(cx, left + c.width(text, 13) / 2), right - c.width(text, 13) / 2)
            c.text(tx, top_y - 12, text, size=13, color=p["TEXT"], weight="semibold", anchor="mm")
    if not peak:
        c.text((left + right) / 2, (top + base) / 2, "No reading yet", size=15, color=p["MUTED"], anchor="mm")
