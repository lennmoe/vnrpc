import { el } from "../dom.js";

const SKIPPED_SECTIONS = new Set(["updating", "update", "install", "installing", "how to update"]);

export function parseVersion(tag) {
  const match = /^\s*v?(\d+(?:\.\d+)*)/i.exec(tag || "");
  return match ? match[1].split(".").map(Number) : [];
}

export function isNewer(tag, current) {
  const a = parseVersion(tag);
  const b = parseVersion(current);
  if (!a.length) {
    return false;
  }
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] || 0;
    const y = b[i] || 0;
    if (x !== y) {
      return x > y;
    }
  }
  return false;
}

export function pick(notes, current, { since = null, recent = 0 } = {}) {
  const upTo = notes.filter((n) => !isNewer(n.version, current));
  if (recent) {
    return upTo.slice(0, recent);
  }
  if (since === null) {
    return upTo.filter((n) => !isNewer(current, n.version)).slice(0, 1);
  }
  return upTo.filter((n) => isNewer(n.version, since));
}

export function clean(body, version) {
  const out = [];
  let skipLevel = 0;

  for (const line of body.replace(/\r\n/g, "\n").split("\n")) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line.trim());

    if (heading) {
      const level = heading[1].length;
      const title = heading[2].trim();
      if (skipLevel && level > skipLevel) {
        continue;
      }
      skipLevel = 0;
      if (SKIPPED_SECTIONS.has(title.toLowerCase().replace(/:$/, ""))) {
        skipLevel = level;
        continue;
      }
      const nothingYet = !out.some((l) => l.trim());
      if (nothingYet && version && title.includes(version)) {
        continue;
      }
    } else if (skipLevel) {
      continue;
    }
    out.push(line);
  }
  return out.join("\n").trim();
}

function inline(text) {
  const plain = text.replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/`([^`]*)`/g, "$1");
  return plain.split(/\*\*|__/).map((piece, i) => (i % 2 ? el("b", {}, piece) : piece));
}

export function renderMarkdown(body) {
  const out = [];
  let list = null;

  for (const raw of body.replace(/\r\n/g, "\n").split("\n")) {
    const heading = /^\s*(#{1,6})\s+(.*)$/.exec(raw);
    const bullet = /^(\s*)[-*+]\s+(.*)$/.exec(raw);

    if (bullet) {
      if (!list) {
        list = el("ul");
        out.push(list);
      }
      const depth = Math.floor(bullet[1].replace(/\t/g, "    ").length / 2);
      list.append(el("li", { style: { marginLeft: `${depth * 18}px` } }, inline(bullet[2])));
      continue;
    }

    list = null;
    if (heading) {
      out.push(el("h4", {}, inline(heading[2])));
    } else if (raw.trim()) {
      out.push(el("p", {}, inline(raw.trim())));
    }
  }
  return out;
}
