import { $, html } from "../dom.js";
import { isoDay } from "../format.js";
import { invoke, pickSaveFile } from "../tauri.js";
import { register } from "../router.js";
import { store } from "../store.js";
import { resolveTheme } from "../themes.js";
import { call, flashLabel } from "../ui.js";
import { collect, render, MAX_COVERS, PERIODS } from "../components/share-card.js";

const TEMPLATE = `
  <div class="page-head">
    <h2>Share your reading</h2>
    <div class="seg" data-id="period">
      <button data-v="this_week">This week</button>
      <button data-v="last_week">Last week</button>
      <button data-v="this_month">This month</button>
      <button data-v="last_month">Last month</button>
    </div>
  </div>

  <div class="share-preview"><canvas data-id="canvas"></canvas></div>

  <div class="row">
    <button class="btn" data-id="copy">Copy image</button>
    <button class="btn secondary" data-id="save">Save…</button>
    <span class="muted">Then paste it in a Discord message with Ctrl+V.</span>
  </div>
`;

let root;
let periodKind = "this_week";
let drawing = 0;

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  for (const button of part("period").querySelectorAll("button")) {
    button.onclick = () => {
      periodKind = button.dataset.v;
      draw();
    };
  }
  part("copy").onclick = copy;
  part("save").onclick = save;
}

function loadImage(src) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = src;
  });
}

async function learnNsfw(vns) {
  const unknown = vns.filter((vn) => vn.nsfw === null).map((vn) => vn.key);
  if (!unknown.length) {
    return;
  }
  try {
    const learned = await invoke("learn_cover_nsfw", { keys: unknown });
    for (const vn of vns) {
      if (vn.key in learned) {
        vn.nsfw = learned[vn.key];
      }
    }
  } catch {}
}

async function draw() {
  const job = ++drawing;
  for (const button of part("period").querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.v === periodKind);
  }
  part("copy").disabled = true;

  const games = await call("share_games");
  const data = collect(games, periodKind);
  const shown = data.vns.slice(0, MAX_COVERS);
  const allowNsfw = !!store.settings.allow_nsfw_covers;

  if (!allowNsfw) {
    await learnNsfw(shown);
  }

  const covers = new Map();
  await Promise.all(
    shown
      .filter((vn) => vn.cover)
      .map(async (vn) => {
        const url = await invoke("image_data_url", {
          path: vn.cover,
          width: 288,
          height: 408,
        }).catch(() => null);
        const image = url && (await loadImage(url));
        if (image) {
          covers.set(vn.key, image);
        }
      }),
  );

  const icon = await loadImage("assets/app_icon.png");
  if (job !== drawing) {
    return;
  }

  const palette = resolveTheme(store.settings.theme || "system", store.settings.custom_theme);
  render(part("canvas"), data, { palette, covers, icon, allowNsfw });
  part("copy").disabled = false;
}

async function copy() {
  await call("copy_png", { dataUrl: part("canvas").toDataURL("image/png") });
  flashLabel(part("copy"), "Copied ✓", "Copy image");
}

async function save() {
  const name = `vn-${PERIODS[periodKind].toLowerCase().replace(" ", "-")}-${isoDay(new Date())}.png`;
  const path = await pickSaveFile({
    title: "Save the card",
    defaultPath: name,
    filters: [{ name: "PNG image", extensions: ["png"] }],
  });
  if (path) {
    await call("save_png", { path, dataUrl: part("canvas").toDataURL("image/png") });
  }
}

register({
  id: "share",
  fill: true,
  build,
  show: draw,
  onKey: (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "c") {
      copy();
    }
  },
});
