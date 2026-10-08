import { $, el, html } from "../dom.js";
import { plural, shortMonth } from "../format.js";
import { fileUrl, invoke } from "../tauri.js";
import { register, show } from "../router.js";
import { subscribe } from "../store.js";
import { call, flashLabel } from "../ui.js";

const BATCH = 60;
const ALL = "";

const TEMPLATE = `
  <button class="back" data-id="back" hidden>← Back</button>

  <div class="page-head">
    <div class="row">
      <h2>Screenshots</h2>
      <span class="muted" data-id="count"></span>
    </div>
    <div class="row">
      <select data-id="game"></select>
      <button class="btn secondary" data-id="folder">Open folder</button>
    </div>
  </div>

  <div class="gallery">
    <div class="card viewer">
      <div class="viewer-image" data-id="image"></div>
      <div class="viewer-info">
        <div>
          <b data-id="caption"></b>
          <div class="muted small-text" data-id="meta"></div>
        </div>
        <div class="row" data-id="actions">
          <button class="btn" data-id="copy">Copy</button>
          <button class="btn secondary" data-id="open">Open</button>
          <button class="btn secondary" data-id="reveal">Show in folder</button>
          <button class="btn danger" data-id="delete">Delete</button>
        </div>
      </div>
    </div>

    <div class="side-strip" data-id="strip"></div>
  </div>
`;

let root;
let games = [];
let names = new Map();
let filterKey = ALL;
let shots = [];
let index = -1;
let shownCount = 0;
let backTo = null;
let backKey = "";
let hotkey = "";

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("back").onclick = goBack;
  part("game").onchange = (event) => {
    filterKey = event.target.value;
    index = -1;
    reload();
  };
  part("folder").onclick = () => call("open_screenshot_folder", { key: filterKey || null });
  part("copy").onclick = copy;
  part("open").onclick = openCurrent;
  part("reveal").onclick = () =>
    currentShot() && call("show_in_folder", { path: currentShot().path });
  part("delete").onclick = remove;
  part("image").ondblclick = openCurrent;

  subscribe("screenshots", () => root.classList.contains("active") && reload());
}

function goBack() {
  if (backTo === "game") {
    show("game", { key: backKey });
  }
}

async function showPage({ key = ALL, select = null, back = null } = {}) {
  backTo = back;
  backKey = key;
  part("back").hidden = !back;
  filterKey = key || ALL;
  index = -1;
  await reload(select);
}

function currentShot() {
  return shots[index] || null;
}

async function reload(select = null) {
  const keep = select || currentShot()?.path;
  const data = await call("list_screenshots", { key: filterKey || null });

  games = data.games;
  hotkey = data.hotkey;
  names = new Map(games.map((g) => [g.key, g.name]));
  if (data.extra) {
    names.set(data.extra.key, data.extra.name);
  }

  renderMenu(data.extra);

  const visible = games.filter((g) => filterKey === ALL || g.key === filterKey);
  shots = visible.flatMap((g) => g.shots.map((path) => ({ key: g.key, path })));
  part("count").textContent = shots.length ? plural(shots.length, "screenshot") : "";

  const wanted = shots.findIndex((s) => s.path === keep);
  fillStrip(visible, Math.max(BATCH, wanted + 1));
  selectShot(wanted >= 0 ? wanted : shots.length ? 0 : -1);
}

function renderMenu(extra) {
  const options = [el("option", { value: ALL }, "All games")];
  for (const game of games) {
    options.push(el("option", { value: game.key }, `${game.name}  (${game.shots.length})`));
  }
  if (extra) {
    options.push(el("option", { value: extra.key }, extra.name));
  }
  part("game").replaceChildren(...options);
  part("game").value = filterKey;
}

function fillStrip(visible, upto) {
  const strip = part("strip");
  strip.replaceChildren();
  shownCount = 0;

  const grouped = filterKey === ALL && visible.length > 1;
  let n = 0;

  for (const game of visible) {
    if (n >= upto) {
      break;
    }
    if (grouped) {
      strip.append(el("div", { class: "group" }, game.name));
    }
    for (const path of game.shots) {
      if (n >= upto) {
        break;
      }
      strip.append(tile(path, n));
      n += 1;
    }
  }
  shownCount = n;

  if (n < shots.length) {
    const rest = Math.min(shots.length - n, BATCH);
    const more = el("button", { class: "btn secondary small" }, `Show ${rest} more`);
    more.onclick = () => {
      fillStrip(visible, shownCount + BATCH);
      highlight();
    };
    strip.append(more);
  }
}

function tile(path, i) {
  const img = el("img", { alt: "" });
  const button = el("button", { class: "tile", "data-index": i }, img);
  button.onclick = () => selectShot(i);
  button.ondblclick = () => {
    selectShot(i);
    openCurrent();
  };

  invoke("thumbnail", { path, width: 420, height: 236 })
    .then((thumb) => (img.src = fileUrl(thumb)))
    .catch(() => {});
  return button;
}

function highlight() {
  for (const button of part("strip").querySelectorAll(".tile")) {
    const on = Number(button.dataset.index) === index;
    button.classList.toggle("on", on);
    if (on) {
      button.scrollIntoView({ block: "nearest" });
    }
  }
}

function emptyViewer() {
  const hint = hotkey
    ? `Press ${hotkey} while reading to capture the game's window.`
    : "Pick a screenshot key in Settings to capture the game's window.";

  part("image").replaceChildren(
    el(
      "div",
      { class: "viewer-empty" },
      el("b", {}, "No screenshots yet"),
      el("div", { class: "muted small-text" }, hint),
    ),
  );
  part("caption").textContent = "";
  part("meta").textContent = "";
}

function formatTaken(text) {
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${date.getDate()} ${shortMonth(date)} ${date.getFullYear()}, ${time}`;
}

async function selectShot(i) {
  index = i;
  const shot = currentShot();
  for (const button of part("actions").querySelectorAll("button")) {
    button.disabled = !shot;
  }

  if (!shot) {
    emptyViewer();
    return;
  }

  if (i >= shownCount) {
    fillStrip(
      games.filter((g) => filterKey === ALL || g.key === filterKey),
      i + 1,
    );
  }
  highlight();

  part("image").replaceChildren(el("img", { src: fileUrl(shot.path), alt: "" }));

  const info = await call("screenshot_info", { path: shot.path });
  if (currentShot() !== shot) {
    return;
  }
  const game = names.get(shot.key) || shot.key;
  part("caption").textContent = info.section ? `${game}  ·  ${info.section}` : game;

  const bits = [formatTaken(info.taken)];
  if (info.width) {
    bits.push(`${info.width}×${info.height}`);
  }
  bits.push(info.file_name);
  part("meta").textContent = bits.join("   ·   ");
}

function step(delta) {
  if (shots.length) {
    selectShot(Math.min(Math.max(0, index + delta), shots.length - 1));
  }
}

async function copy() {
  const shot = currentShot();
  if (!shot) {
    return;
  }
  await call("copy_image_file", { path: shot.path });
  flashLabel(part("copy"), "Copied ✓", "Copy");
}

function openCurrent() {
  const shot = currentShot();
  if (shot) {
    call("open_path", { path: shot.path });
  }
}

async function remove() {
  const shot = currentShot();
  if (!shot) {
    return;
  }

  const after = shots[index + 1]?.path || shots[index - 1]?.path || null;
  await call("delete_screenshot", { key: shot.key, path: shot.path });
  index = -1;
  await reload(after);
}

function onKey(event) {
  const actions = {
    ArrowLeft: () => step(-1),
    ArrowUp: () => step(-1),
    ArrowRight: () => step(1),
    ArrowDown: () => step(1),
    Delete: remove,
    Enter: openCurrent,
    Escape: goBack,
  };

  if (event.ctrlKey && event.key.toLowerCase() === "c") {
    copy();
  } else if (!event.ctrlKey && actions[event.key]) {
    actions[event.key]();
  } else {
    return;
  }
  event.preventDefault();
}

register({ id: "screenshots", fill: true, build, show: showPage, onKey });
