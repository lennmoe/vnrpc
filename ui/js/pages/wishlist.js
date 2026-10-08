import { $, el, html } from "../dom.js";
import { register, show } from "../router.js";
import { store } from "../store.js";
import { call, setCover } from "../ui.js";

const STALE_AFTER_MS = 10 * 60 * 1000;

const TEMPLATE = `
  <button class="back" data-id="back">← Library</button>

  <div class="card wish">
    <div class="cover" data-id="cover"></div>
    <div class="info">
      <div class="eyebrow">Random pick from your VNDB wishlist</div>
      <h1 data-id="title"></h1>
      <div class="muted" data-id="alt"></div>
      <div class="chips" data-id="chips"></div>
      <div class="subtle small-text" data-id="status"></div>

      <div class="row actions">
        <button class="btn" data-id="next">Another one</button>
        <button class="btn secondary" data-id="vndb">VNDB page ↗</button>
        <span class="subtle small-text">Space: another one</span>
      </div>
    </div>
  </div>
`;

let root;
let order = [];
let position = -1;
let total = 0;
let loadedAt = 0;
let loading = false;

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("back").onclick = () => show("library");
  part("next").onclick = next;
  part("vndb").onclick = () =>
    current() && call("open_url", { url: `https://vndb.org/${current().id}` });
  setReady(false);
}

function setReady(ready) {
  part("next").disabled = !ready;
  part("vndb").disabled = !ready;
}

function current() {
  return order[position] || null;
}

function shuffled(wishlist, inLibrary) {
  const skip = new Set(inLibrary);
  const pool = wishlist.filter((vn) => !skip.has(vn.id));
  const list = pool.length ? pool : [...wishlist];

  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
}

async function load() {
  if (loading || (order.length && Date.now() - loadedAt < STALE_AFTER_MS)) {
    return;
  }
  loading = true;
  if (!order.length) {
    part("title").textContent = "";
    part("status").textContent = "Loading your wishlist…";
  }

  try {
    const { wishlist, in_library } = await call("get_wishlist");
    loadedAt = Date.now();

    if (!wishlist.length) {
      order = [];
      setReady(false);
      part("title").textContent = "Your wishlist is empty";
      part("status").textContent = "Add VNs to your Wishlist on vndb.org, then come back.";
      return;
    }

    const shown = current();
    order = shuffled(wishlist, in_library);
    total = wishlist.length;
    setReady(true);

    const keep = shown ? order.findIndex((vn) => vn.id === shown.id) : -1;
    if (keep >= 0) {
      position = keep;
      render();
    } else {
      position = -1;
      next();
    }
  } catch (error) {
    if (!order.length) {
      part("title").textContent = "Couldn't load your wishlist";
      part("status").textContent = String(error);
    }
  } finally {
    loading = false;
  }
}

function next() {
  if (!order.length) {
    return;
  }
  position += 1;

  if (position >= order.length) {
    const last = order[order.length - 1];
    order = shuffled(order, []);
    if (order.length > 1 && order[0] === last) {
      [order[0], order[1]] = [order[1], order[0]];
    }
    position = 0;
  }
  render();
}

function lengthText(minutes) {
  if (minutes <= 0) {
    return "";
  }
  const hours = minutes / 60;
  if (hours >= 2) {
    return `~${Math.round(hours)}h`;
  }
  return minutes < 60 ? `~${minutes}m` : `~${hours.toFixed(1)}h`;
}

function render() {
  const vn = current();
  part("title").textContent = vn.title;
  part("alt").textContent = vn.alt_title !== vn.title ? vn.alt_title : "";

  const rating = vn.rating > 10 ? vn.rating / 10 : vn.rating;
  const chips = [
    vn.year,
    vn.rating > 0 && `Rating ${rating.toFixed(1)}`,
    lengthText(vn.length_minutes),
  ];
  part("chips").replaceChildren(
    ...chips.filter(Boolean).map((text) => el("span", { class: "chip quiet" }, text)),
  );

  const skipped = total - order.length;
  part("status").textContent =
    `${position + 1} / ${order.length} on your wishlist` +
    (skipped ? `  ·  ${skipped} already in your Library skipped` : "");

  setCover(part("cover"), {
    url: vn.image_url,
    nsfw: vn.nsfw && !store.settings.allow_nsfw_covers,
    label: vn.title,
  });
}

register({
  id: "wishlist",
  nav: "library",
  build,
  show: load,
  onKey: (event) => {
    if (event.key === "Escape") {
      show("library");
    } else if (event.key === " ") {
      event.preventDefault();
      next();
    }
  },
});
