import { $, el, html } from "../dom.js";
import { capitalize, formatPlaytime, isoDay, addDays, lastPlayed, plural } from "../format.js";
import { register, show } from "../router.js";
import { store, subscribe } from "../store.js";
import { call, confirmButton, segmented, setCover, toast } from "../ui.js";
import { playGame } from "../components/play.js";

const TEMPLATE = `
  <div class="page-head lib-head">
    <h2>Library</h2>
    <input type="search" data-id="filter" placeholder="Filter…" />
  </div>

  <div class="page-head">
    <div class="seg" data-id="sort">
      <button data-v="most">Most read</button>
      <button data-v="recent">Recent</button>
      <button data-v="az">A–Z</button>
    </div>
    <div class="row">
      <button class="btn secondary" data-id="wishlist">Random from wishlist</button>
      <select data-id="status">
        <option value="">All statuses</option>
        <option value="playing">Playing</option>
        <option value="finished">Finished</option>
        <option value="stalled">Stalled</option>
        <option value="dropped">Dropped</option>
      </select>
    </div>
  </div>

  <div class="muted" data-id="summary"></div>
  <div class="lib-list" data-id="list"></div>
`;

const SORTERS = {
  most: (a, b) => b.playtime - a.playtime,
  recent: (a, b) => b.last_played - a.last_played,
  az: (a, b) => a.name.localeCompare(b.name),
};

let root;
let games = [];
let sort = "most";

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("filter").oninput = render;
  part("status").onchange = render;
  part("wishlist").onclick = () => show("wishlist");

  subscribe("library", () => root.classList.contains("active") && load());
  subscribe("settings", () => root.classList.contains("active") && load());
}

async function load() {
  games = await call("get_library");
  render();
}

function weekSeconds(daily) {
  const today = new Date();
  let total = 0;
  for (let back = 0; back < 7; back++) {
    total += daily[isoDay(addDays(today, -back))] || 0;
  }
  return total;
}

function render() {
  segmented(part("sort"), sort, (value) => {
    sort = value;
    render();
  });

  const filter = part("filter").value.trim().toLowerCase();
  const status = part("status").value;
  const shown = games
    .filter((game) => !filter || game.name.toLowerCase().includes(filter))
    .filter((game) => !status || game.status === status)
    .sort(SORTERS[sort]);

  const total = games.reduce((sum, game) => sum + game.playtime, 0);
  const week = games.reduce((sum, game) => sum + weekSeconds(game.daily), 0);
  part("summary").textContent =
    `${plural(games.length, "game")}  ·  ${formatPlaytime(total)} read in total  ·  ${formatPlaytime(week)} this week`;

  if (!shown.length) {
    const message = games.length ? "Nothing matches." : "The VNs you read will show up here.";
    part("list").replaceChildren(el("div", { class: "card lib-empty" }, message));
    return;
  }

  const most = Math.max(1, ...games.map((game) => game.playtime));
  part("list").replaceChildren(...shown.map((game) => row(game, most)));
}

function row(game, most) {
  const cover = el("div", { class: "cover small" });
  setCover(cover, { path: game.cover, nsfw: game.nsfw, label: game.name });

  const meta = el(
    "div",
    { class: "meta" },
    game.status && el("span", { class: `status ${game.status}` }, capitalize(game.status)),
    el("span", {}, `${formatPlaytime(game.playtime)} read`),
    game.last_played > 0 && el("span", {}, `·  ${lastPlayed(game.last_played)}`),
    game.vndb_id && el("span", {}, `·  ${game.vndb_id}`),
  );

  const bar = el(
    "div",
    { class: "bar" },
    el("i", { style: { width: `${(game.playtime / most) * 100}%` } }),
  );

  const play = el("button", { class: "btn small" }, "▶  Play");
  play.onclick = (event) => {
    event.stopPropagation();
    playGame(game.key);
  };
  play.hidden = !game.has_path;

  const remove = el("button", { class: "btn danger small" });
  confirmButton(remove, "Remove", async () => {
    await call("remove_game", { key: game.key });
    toast(`${game.name} was removed (its screenshots are kept)`);
  });

  const open = () => show("game", { key: game.key });
  const onkeydown = (event) => event.key === "Enter" && open();

  return el(
    "div",
    { class: "card lib-row", role: "button", tabindex: "0", onclick: open, onkeydown },
    cover,
    el("div", { class: "info" }, el("div", { class: "name" }, game.name), meta, bar),
    el("div", { class: "actions" }, play, remove),
  );
}

register({ id: "library", build, show: load });
