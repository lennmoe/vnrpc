import {
  addDays,
  formatPlaytime,
  isoDay,
  midnight,
  monthName,
  parseDay,
  shortMonth,
} from "../format.js";

export const PERIODS = {
  this_week: "This week",
  last_week: "Last week",
  this_month: "This month",
  last_month: "Last month",
};

export const WIDTH = 1280;
export const HEIGHT = 720;
export const MAX_COVERS = 5;

const PAD = 56;
const COVER_W = 144;
const COVER_H = 204;
const COVER_GAP = 20;
const CHART_W = 300;
const FONT = '"Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif';

function period(kind, today) {
  if (kind === "this_week" || kind === "last_week") {
    let monday = addDays(today, -((today.getDay() + 6) % 7));
    if (kind === "last_week") {
      monday = addDays(monday, -7);
    }
    return [monday, addDays(monday, 6)];
  }

  let first = new Date(today.getFullYear(), today.getMonth(), 1);
  if (kind === "last_month") {
    first = new Date(first.getFullYear(), first.getMonth() - 1, 1);
  }
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
  return [first, last];
}

function finishedBetween(game, start, end) {
  if (game.status !== "finished") {
    return false;
  }
  const stamp = game.finished_at || game.last_played;
  if (!stamp) {
    return false;
  }
  const day = midnight(new Date(stamp * 1000));
  return day >= start && day <= end;
}

export function collect(games, kind, today = midnight(new Date())) {
  const [start, end] = period(kind, today);
  const last = end < today ? end : today;
  const weekly = kind === "this_week" || kind === "last_week";

  const title = weekly ? "My week in visual novels" : `My ${monthName(start)} in visual novels`;
  const subtitle =
    start.getMonth() === end.getMonth()
      ? `${start.getDate()} – ${end.getDate()} ${shortMonth(end)} ${end.getFullYear()}`
      : `${start.getDate()} ${shortMonth(start)} – ${end.getDate()} ${shortMonth(end)} ${end.getFullYear()}`;

  const days = [];
  for (let day = start; day <= end; day = addDays(day, 1)) {
    days.push({ day, seconds: 0 });
  }
  const byKey = new Map(days.map((d) => [isoDay(d.day), d]));

  const vns = [];
  for (const game of games) {
    let seconds = 0;
    for (const [dayKey, secs] of Object.entries(game.daily || {})) {
      const day = parseDay(dayKey);
      if (day >= start && day <= last) {
        seconds += secs;
        byKey.get(dayKey).seconds += secs;
      }
    }

    const finished = finishedBetween(game, start, last);
    if (seconds > 0 || finished) {
      vns.push({ ...game, seconds, finished });
    }
  }
  vns.sort((a, b) => b.seconds - a.seconds || Number(b.finished) - Number(a.finished));

  return {
    kind,
    weekly,
    title,
    subtitle,
    totalSeconds: days.reduce((sum, d) => sum + d.seconds, 0),
    daysRead: days.filter((d) => d.seconds > 0).length,
    daysSoFar: Math.max(0, Math.round((last - start) / 86400000) + 1),
    vns,
    days,
  };
}

function font(size, weight = 400) {
  return `${weight} ${size}px ${FONT}`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function fit(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) {
    return text;
  }
  let cut = text;
  while (cut && ctx.measureText(cut + "…").width > maxWidth) {
    cut = cut.slice(0, -1);
  }
  return cut.trimEnd() + "…";
}

function wrap(ctx, text, maxWidth, lines = 2) {
  const out = [];
  let rest = text.trim();

  while (rest && out.length < lines - 1) {
    let cut = rest.length;
    while (cut > 1 && ctx.measureText(rest.slice(0, cut)).width > maxWidth) {
      cut -= 1;
    }
    if (cut < rest.length) {
      const space = rest.slice(0, cut + 1).lastIndexOf(" ");
      if (space > 0) {
        cut = space;
      }
    }
    out.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }

  if (rest) {
    out.push(fit(ctx, rest, maxWidth));
  }
  return out;
}

export function render(canvas, data, { palette: p, covers, icon, allowNsfw }) {
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  ctx.textBaseline = "top";

  ctx.fillStyle = p.BG;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  drawHeader(ctx, data, p, icon);
  drawTiles(ctx, data, p);
  drawCovers(ctx, data, p, covers, allowNsfw);
  drawChart(ctx, data, p, WIDTH - PAD - CHART_W, 304, CHART_W, HEIGHT - PAD - 304);
}

function drawHeader(ctx, data, p, icon) {
  ctx.fillStyle = p.TEXT;
  ctx.font = font(42, 700);
  ctx.fillText(fit(ctx, data.title, WIDTH - 2 * PAD - 260), PAD, 44);

  ctx.fillStyle = p.MUTED;
  ctx.font = font(22);
  ctx.fillText(data.subtitle, PAD, 104);

  const brand = "Visual Novel RPC";
  ctx.font = font(17, 600);
  const brandX = WIDTH - PAD - ctx.measureText(brand).width;
  ctx.textBaseline = "middle";
  ctx.fillText(brand, brandX, 66);
  ctx.textBaseline = "top";

  if (icon) {
    ctx.save();
    roundRect(ctx, brandX - 42, 50, 32, 32, 8);
    ctx.clip();
    ctx.drawImage(icon, brandX - 42, 50, 32, 32);
    ctx.restore();
  }
}

function drawTiles(ctx, data, p) {
  const finished = data.vns.filter((vn) => vn.finished).length;
  const tiles = [
    ["TIME READ", formatPlaytime(data.totalSeconds), p.TEXT],
    ["VISUAL NOVELS", String(data.vns.filter((vn) => vn.seconds).length), p.TEXT],
    ["FINISHED", String(finished), finished ? p.GREEN : p.TEXT],
    ["DAYS READ", `${data.daysRead} / ${data.daysSoFar}`, p.TEXT],
  ];

  const gap = 20;
  const top = 160;
  const height = 112;
  const width = (WIDTH - 2 * PAD - gap * (tiles.length - 1)) / tiles.length;

  tiles.forEach(([label, value, color], i) => {
    const x = PAD + i * (width + gap);

    roundRect(ctx, x, top, width, height, 16);
    ctx.fillStyle = p.SURFACE;
    ctx.fill();
    ctx.strokeStyle = p.BORDER;
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = p.SUBTLE;
    ctx.font = font(14, 700);
    ctx.fillText(label, x + 24, top + 22);

    ctx.fillStyle = color;
    ctx.font = font(38, 700);
    ctx.fillText(value, x + 24, top + 46);
  });
}

function drawCovers(ctx, data, p, covers, allowNsfw) {
  const top = 304;
  const shown = data.vns.slice(0, MAX_COVERS);

  if (!shown.length) {
    const leftWidth = WIDTH - 2 * PAD - CHART_W - 40;
    ctx.fillStyle = p.MUTED;
    ctx.font = font(26, 600);
    ctx.textAlign = "center";
    ctx.fillText(
      `Nothing read this ${data.weekly ? "week" : "month"}`,
      PAD + leftWidth / 2,
      top + 136,
    );
    ctx.textAlign = "left";
    return;
  }

  shown.forEach((vn, i) => {
    const x = PAD + i * (COVER_W + COVER_GAP);
    drawCover(ctx, vn, covers.get(vn.key), x, top, p, allowNsfw);

    if (vn.finished) {
      roundRect(ctx, x - 2, top - 2, COVER_W + 4, COVER_H + 4, 14);
      ctx.strokeStyle = p.GREEN;
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.font = font(12, 700);
      const badge = ctx.measureText("FINISHED").width + 16;
      roundRect(ctx, x + 8, top + 8, badge, 24, 12);
      ctx.fillStyle = p.GREEN;
      ctx.fill();
      ctx.fillStyle = p.BG;
      ctx.textBaseline = "middle";
      ctx.fillText("FINISHED", x + 16, top + 20);
      ctx.textBaseline = "top";
    }

    let y = top + COVER_H + 12;
    ctx.font = font(16, 600);
    ctx.fillStyle = p.TEXT;
    for (const line of wrap(ctx, vn.name, COVER_W)) {
      ctx.fillText(line, x, y);
      y += 22;
    }
    if (vn.seconds) {
      ctx.font = font(15);
      ctx.fillStyle = p.MUTED;
      ctx.fillText(formatPlaytime(vn.seconds), x, y + 2);
    }
  });
}

function drawCover(ctx, vn, image, x, y, p, allowNsfw) {
  ctx.save();
  roundRect(ctx, x, y, COVER_W, COVER_H, 12);
  ctx.clip();

  if (image) {
    if (vn.nsfw && !allowNsfw) {
      ctx.filter = "blur(18px)";
    }
    ctx.drawImage(image, x, y, COVER_W, COVER_H);
  } else {
    ctx.fillStyle = p.SURFACE_ALT;
    ctx.fillRect(x, y, COVER_W, COVER_H);
    ctx.fillStyle = p.SUBTLE;
    ctx.font = font(56, 700);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText((vn.name.trim()[0] || "?").toUpperCase(), x + COVER_W / 2, y + COVER_H / 2);
  }
  ctx.restore();
}

function drawChart(ctx, data, p, x, y, w, h) {
  roundRect(ctx, x, y, w, h, 16);
  ctx.fillStyle = p.SURFACE;
  ctx.fill();
  ctx.strokeStyle = p.BORDER;
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.fillStyle = p.SUBTLE;
  ctx.font = font(14, 700);
  ctx.fillText("PER DAY", x + 20, y + 20);

  const left = x + 20;
  const right = x + w - 20;
  const top = y + 64;
  const base = y + h - 40;

  ctx.strokeStyle = p.BORDER;
  ctx.beginPath();
  ctx.moveTo(left, base);
  ctx.lineTo(right, base);
  ctx.stroke();

  const days = data.days;
  const peak = Math.max(0, ...days.map((d) => d.seconds));
  const slot = (right - left) / days.length;
  const bar = Math.max(3, Math.min(22, slot - 4));

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  days.forEach(({ day, seconds }, i) => {
    const center = left + slot * (i + 0.5);

    if (data.weekly || [1, 8, 15, 22, 29].includes(day.getDate())) {
      ctx.fillStyle = p.MUTED;
      ctx.font = font(13);
      ctx.fillText(data.weekly ? "MTWTFSS"[i] : String(day.getDate()), center, base + 18);
    }
    if (seconds <= 0 || !peak) {
      return;
    }

    const topY = base - ((base - top) * seconds) / peak;
    ctx.fillStyle = p.ACCENT;
    roundRect(ctx, center - bar / 2, topY, bar, base - topY, Math.min(bar / 2, 5));
    ctx.fill();

    if (seconds === peak) {
      const label = formatPlaytime(seconds);
      ctx.font = font(13, 600);
      const half = ctx.measureText(label).width / 2;
      const labelX = Math.min(Math.max(center, left + half), right - half);
      ctx.fillStyle = p.TEXT;
      ctx.fillText(label, labelX, topY - 12);
    }
  });

  if (!peak) {
    ctx.fillStyle = p.MUTED;
    ctx.font = font(15);
    ctx.fillText("No reading yet", (left + right) / 2, (top + base) / 2);
  }

  ctx.textAlign = "left";
  ctx.textBaseline = "top";
}
