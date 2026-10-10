import { $, el, html } from "../dom.js";
import { register, show } from "../router.js";
import { store } from "../store.js";
import { ask, call, openDialog, segmented, setCover, toast } from "../ui.js";

const PRIVACY_HELP = {
  full: "Discord shows the name, the current section and the cover.",
  partial: "Discord shows the name and cover, but not where you are in the story.",
  private: "Discord only shows a generic “Visual Novel” — no name, no cover.",
  off: "Nothing is shared on Discord while this game is open.",
};

const RELEASE_TYPES = {
  pkgfront: "Front",
  pkgback: "Back",
  pkgside: "Side",
  pkgmed: "Medium",
  dig: "Digital",
};

const TEMPLATE = `
  <button class="back" data-id="back">← Back</button>
  <h2 data-id="title"></h2>

  <div class="card">
    <div class="field">
      <b>Discord privacy for this game</b>
      <div class="seg" data-id="privacy">
        <button data-v="full">Full</button>
        <button data-v="partial">Partial</button>
        <button data-v="private">Private</button>
        <button data-v="off">Off</button>
      </div>
    </div>
    <div class="hint-text" data-id="privacy-help"></div>
  </div>

  <div class="card">
    <div class="tabs" data-id="tabs">
      <button data-tab="vndb">Search VNDB</button>
      <button data-tab="url">Image link</button>
    </div>

    <div data-tab-body="vndb">
      <form class="row" data-id="search-form" style="margin: 14px 0 6px">
        <input type="search" class="wide" data-id="query" placeholder="Visual novel title…" />
        <button class="btn" type="submit">Search</button>
      </form>
      <div class="hint-text" data-id="search-status"></div>
      <div class="vn-results" data-id="results"></div>
    </div>

    <div data-tab-body="url" hidden>
      <p class="muted small-text" style="margin-top: 14px">
        A direct link to a public image (jpg / png / webp). This link is what Discord will display.
      </p>
      <input type="text" class="wide" data-id="url" placeholder="https://…" style="width: 100%" />
      <div class="preview-area">
        <div class="cover preview" data-id="url-preview"></div>
        <div class="row">
          <button class="btn secondary" data-id="url-show">Preview</button>
          <button class="btn" data-id="url-use">Use this image</button>
        </div>
        <div class="hint-text" data-id="url-status"></div>
      </div>
    </div>
  </div>
`;

let root;
let key = "";
let backTo = "home";

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("back").onclick = goBack;
  for (const tab of root.querySelectorAll("[data-tab]")) {
    tab.onclick = () => openTab(tab.dataset.tab);
  }

  part("search-form").onsubmit = (event) => {
    event.preventDefault();
    search();
  };

  part("url-show").onclick = previewUrl;
  part("url-use").onclick = useUrl;
  part("url").onkeydown = (event) => event.key === "Enter" && previewUrl();

}

async function showPage({ key: wanted, back = "home" }) {
  key = wanted;
  backTo = back;

  const game = await call("get_game", { key });
  part("title").textContent = `Cover & privacy — ${game.name}`;

  renderPrivacy(game.entry.privacy || "full");
  openTab("vndb");

  part("query").value = game.name;
  part("url").value = "";
  setCover(part("url-preview"));
  part("url-status").textContent = "";
  search();
}

function goBack() {
  if (backTo === "game") {
    show("game", { key });
  } else {
    show("home");
  }
}

function openTab(name) {
  for (const tab of root.querySelectorAll("[data-tab]")) {
    tab.classList.toggle("on", tab.dataset.tab === name);
  }
  for (const body of root.querySelectorAll("[data-tab-body]")) {
    body.hidden = body.dataset.tabBody !== name;
  }
}

function renderPrivacy(value) {
  part("privacy-help").textContent = PRIVACY_HELP[value] || "";
  segmented(part("privacy"), value, async (picked) => {
    await call("update_game", { key, fields: { privacy: picked } });
    renderPrivacy(picked);
  });
}

async function okToUseNsfw(nsfw) {
  if (!nsfw || store.settings.allow_nsfw_covers) {
    return true;
  }
  return ask(
    "NSFW cover",
    "VNDB flags this cover as NSFW. It will be shown blurred in the app and NOT sent to Discord " +
      "unless you allow NSFW covers in Settings. Use it anyway?",
    { yes: "Use it" },
  );
}

async function done(message) {
  toast(message);
  goBack();
}

async function search() {
  const query = part("query").value.trim();
  if (!query) {
    return;
  }

  part("search-status").textContent = "Searching…";
  part("results").replaceChildren();

  let results;
  try {
    results = await call("search_vndb", { query });
  } catch {
    part("search-status").textContent = "Search failed.";
    return;
  }

  part("search-status").textContent = results.length
    ? `${results.length} result${results.length === 1 ? "" : "s"}`
    : "No results — try the original (Japanese) or a shorter title.";
  part("results").replaceChildren(...results.map(resultRow));
}

function rating(value) {
  return value > 10 ? (value / 10).toFixed(1) : value.toFixed(1);
}

function resultRow(vn) {
  const picture = el("div", { class: "cover tiny" });
  setCover(picture, { url: vn.image_url, nsfw: vn.nsfw, label: vn.title });

  const chips = el(
    "div",
    { class: "chips" },
    el("span", { class: "chip quiet" }, vn.id),
    vn.rating > 0 && el("span", { class: "chip quiet" }, `★ ${rating(vn.rating)}`),
    vn.nsfw && el("span", { class: "chip warn" }, "NSFW cover"),
  );

  const title = vn.year ? `${vn.title}  (${vn.year})` : vn.title;
  const info = el(
    "div",
    { class: "info" },
    el("div", { class: "title" }, title),
    vn.alt_title && el("div", { class: "muted small-text" }, vn.alt_title),
    chips,
  );

  const buttons = el(
    "div",
    { class: "row" },
    el(
      "button",
      { class: "btn secondary small", onclick: () => releaseCovers(vn) },
      "Other covers…",
    ),
    el("button", { class: "btn small", onclick: () => useVn(vn) }, "Use"),
  );

  return el("div", { class: "card vn-result" }, picture, info, buttons);
}

async function useVn(vn) {
  if (!(await okToUseNsfw(vn.nsfw))) {
    return;
  }
  await call("set_game_vn", { key, vnId: vn.id, title: vn.title });
  done(`Now using ${vn.title}`);
}

async function releaseCovers(vn) {
  const grid = el(
    "div",
    { class: "release-grid" },
    el("div", { class: "muted" }, "Loading releases…"),
  );
  let closeDialog = () => {};

  const dialog = openDialog({
    title: `Release covers — ${vn.title}`,
    body: grid,
    wide: true,
    actions: [{ label: "Close", kind: "secondary", value: null }],
    onOpen: (close) => (closeDialog = close),
  });

  let covers;
  try {
    covers = await call("release_covers", { vnId: vn.id });
  } catch {
    grid.replaceChildren(el("div", { class: "error-text" }, "Couldn't load the releases."));
    return;
  }

  if (!covers.length) {
    grid.replaceChildren(
      el("div", { class: "muted" }, "No other release covers found for this VN."),
    );
    return;
  }

  grid.replaceChildren(
    ...covers.map((cover) => {
      const picture = el("div", { class: "cover" });
      setCover(picture, { url: cover.url, nsfw: cover.nsfw });

      const caption =
        (RELEASE_TYPES[cover.kind] || cover.kind || "Cover") + (cover.nsfw ? " · NSFW" : "");

      const use = async () => {
        if (!(await okToUseNsfw(cover.nsfw))) {
          return;
        }
        closeDialog(null);
        await call("set_release_cover", { key, vnId: vn.id, title: vn.title, url: cover.url });
        done("Cover changed");
      };

      return el(
        "div",
        { class: "card release-cell" },
        picture,
        el("b", { class: cover.nsfw ? "chip warn" : "" }, caption),
        el("div", { class: "muted small-text" }, cover.release_title),
        el("div", { class: "row" }, el("button", { class: "btn small", onclick: use }, "Use")),
      );
    }),
  );
  await dialog;
}

function linkIsValid(url) {
  return url.startsWith("http://") || url.startsWith("https://");
}

async function previewUrl() {
  const url = part("url").value.trim();
  if (!linkIsValid(url)) {
    part("url-status").textContent = "Enter a http(s) image link.";
    return;
  }

  part("url-status").textContent = "Loading preview…";
  try {
    const image = await call("prepare_image", { source: url });
    setCover(part("url-preview"), { path: image.path });
    part("url-status").textContent = "";
  } catch {
    part("url-status").textContent = "Couldn't load an image from that link.";
  }
}

async function useUrl() {
  const url = part("url").value.trim();
  if (!linkIsValid(url)) {
    toast("Enter a http(s) image link.", { error: true });
    return;
  }
  await call("set_cover_url", { key, url });
  done("Cover changed");
}

register({
  id: "cover",
  nav: "home",
  build,
  show: showPage,
  onKey: (event) => event.key === "Escape" && goBack(),
});
