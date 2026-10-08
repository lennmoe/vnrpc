import { $, el, html } from "../dom.js";
import {
  addDays,
  formatPlaytime,
  isoDay,
  lastPlayed,
  midnight,
  parseDay,
  shortDate,
  weekday,
} from "../format.js";
import { invoke, fileUrl } from "../tauri.js";
import { register, show } from "../router.js";
import { store, subscribe } from "../store.js";
import { call, confirmButton, segmented, setCover, toast } from "../ui.js";
import { drawChart } from "../components/chart.js";
import { LAUNCHERS, locateGame, locateTool, playGame } from "../components/play.js";

const TEMPLATE = `
  <button class="back" data-id="back">← Library</button>

  <div class="game-grid">
    <div class="col">
      <div class="card game-head">
        <div class="cover mid" data-id="cover"></div>
        <div class="details">
          <h2 data-id="name"></h2>
          <div class="subtle path selectable" data-id="path"></div>
          <div class="row" data-id="vndb"></div>
          <button class="link" data-id="change-cover">Change cover & privacy…</button>
        </div>
      </div>

      <div class="card">
        <div class="field">
          <b>Status</b>
          <div class="seg" data-id="status">
            <button data-v="playing">Playing</button>
            <button data-v="finished">Finished</button>
            <button data-v="stalled">Stalled</button>
            <button data-v="dropped">Dropped</button>
          </div>
        </div>
        <div class="field">
          <b>Rating</b>
          <div class="row">
            <span class="muted small-text" data-id="vote-state"></span>
            <select data-id="vote"></select>
          </div>
        </div>
        <div class="hint-text" data-id="vndb-note"></div>
      </div>

      <div class="card">
        <div class="field">
          <b>Launch with</b>
          <div class="seg" data-id="launcher">
            <button data-v="">Normal</button>
            <button data-v="le">Locale Emulator</button>
            <button data-v="ntlea">NTLEA</button>
          </div>
        </div>
        <div class="hint-text" data-id="launcher-note"></div>
      </div>
    </div>

    <div class="col">
      <div class="stats">
        <div class="stat"><span>Total read</span><b data-id="total"></b></div>
        <div class="stat"><span>This week</span><b data-id="week"></b></div>
        <div class="stat"><span>Sessions</span><b data-id="sessions"></b></div>
        <div class="stat"><span>Last played</span><b data-id="last"></b></div>
      </div>

      <button class="link" data-id="edit-total">Edit total read</button>
      <div class="card" data-id="editor" hidden>
        <form class="row" data-id="editor-form">
          <b>Total read</b>
          <input type="number" min="0" data-id="hours" /> h
          <input type="number" min="0" max="59" data-id="minutes" /> min
          <button class="btn small" type="submit">Save</button>
          <button class="btn secondary small" type="button" data-id="editor-cancel">Cancel</button>
        </form>
        <div class="hint-text">
          Time read before the app tracked it, or a correction. The day-by-day history
          (this week, the chart) stays as it is.
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <b>Time read</b>
          <div class="seg" data-id="range">
            <button data-v="days">30 days</button>
            <button data-v="weeks">12 weeks</button>
          </div>
        </div>
        <div data-id="chart"></div>
        <div class="hint-text" data-id="history-note"></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">
      <div class="row"><b>Screenshots</b><span class="muted" data-id="shot-count"></span></div>
      <button class="btn secondary small" data-id="all-shots">View all</button>
    </div>
    <div class="shot-strip" data-id="shots"></div>
    <div class="hint-text" data-id="shots-hint"></div>
  </div>

  <div class="game-footer">
    <button class="btn" data-id="play">▶  Play</button>
    <button class="btn secondary" data-id="locate">Locate…</button>
    <button class="btn danger" data-id="remove"></button>
  </div>
`;

const VOTES = [0];
for (let vote = 100; vote >= 10; vote -= 5) {
  VOTES.push(vote);
}

let root;
let key = "";
let game = null;
let range = "days";

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("back").onclick = () => show("library");
  part("change-cover").onclick = () => show("cover", { key, back: "game" });
  part("all-shots").onclick = () => show("screenshots", { key, back: "game" });
  part("play").onclick = () => playGame(key);
  part("locate").onclick = async () => (await locateGame(key)) && load();
  part("vote").onchange = saveVote;

  part("edit-total").onclick = openEditor;
  part("editor-cancel").onclick = closeEditor;
  part("editor-form").onsubmit = saveTotal;

  subscribe("library", (change) => isShown() && (!change?.key || change.key === key) && load());
  subscribe("screenshots", (change) => isShown() && change?.key === key && load());
}

function isShown() {
  return root.classList.contains("active");
}

async function showPage(params) {
  if (params.key !== key) {
    range = "days";
  }
  key = params.key;
  closeEditor();
  await load();
}

async function load() {
  game = await call("get_game", { key });
  const entry = game.entry;

  part("name").textContent = game.name;
  part("path").textContent = entry.path || "Executable not located yet";
  setCover(part("cover"), { path: game.cover, nsfw: entry.cover_nsfw, label: game.name });

  renderVndb(entry);
  renderStatus(entry);
  renderVote(entry);
  renderLauncher(entry);
  renderStats(entry);
  renderChart();
  renderShots();

  part("play").hidden = !entry.path;
  part("locate").hidden = !!entry.path;
  confirmButton(part("remove"), "Remove", async () => {
    await call("remove_game", { key });
    toast(`${game.name} was removed (its screenshots are kept)`);
    show("library");
  });
}

function renderVndb(entry) {
  const box = part("vndb");
  const vnId = entry.vndb_id;
  const matched = entry.matched_vndb_id;
  const link = (id) =>
    el(
      "button",
      {
        class: "btn secondary small",
        onclick: () => call("open_url", { url: `https://vndb.org/${id}` }),
      },
      `VNDB ${id} ↗`,
    );

  if (vnId) {
    box.replaceChildren(link(vnId));
  } else if (matched) {
    const confirm = el("button", { class: "btn small", onclick: confirmMatch }, "Confirm");
    box.replaceChildren(
      link(matched),
      el("span", { class: "muted small-text" }, "found automatically"),
      confirm,
    );
  } else {
    box.replaceChildren(
      el(
        "span",
        { class: "muted small-text" },
        "Not matched on VNDB — pick it with “Change cover”.",
      ),
    );
  }
}

async function confirmMatch() {
  await call("confirm_match", { key });
  toast("VNDB entry confirmed");
}

function renderStatus(entry) {
  segmented(part("status"), entry.status || "", async (value) => {
    const status = value === entry.status ? "" : value;
    await call("update_game", { key, fields: { status } });
  });
}

function voteLabel(vote) {
  return vote ? String(vote / 10) : "No rating";
}

function renderVote(entry) {
  const canRate = game.has_token && !!entry.vndb_id;
  const select = part("vote");
  const current = entry.vndb_vote || 0;

  const choices = VOTES.includes(current)
    ? VOTES
    : [...VOTES, current].sort((a, b) => (a && b ? b - a : a - b));
  select.replaceChildren(
    ...choices.map((v) => el("option", { value: v, selected: v === current }, voteLabel(v))),
  );
  select.disabled = !canRate;

  let note;
  if (!game.has_token) {
    note = "Add your VNDB token in Settings to rate it and sync its status to your VNDB list.";
  } else if (!entry.vndb_id) {
    note = "Confirm the VNDB match above to rate it and sync it to your VNDB list.";
  } else if (game.vndb_sync) {
    note = "Status and rating are sent to your VNDB list.";
  } else {
    note =
      "The rating is sent to your VNDB list. Turn on list sync in Settings for the status too.";
  }
  part("vndb-note").textContent = note;
  part("vote-state").textContent = "";

  if (canRate) {
    refreshVote();
  }
}

async function refreshVote() {
  const forKey = key;
  part("vote-state").textContent = "Checking VNDB…";
  try {
    const vote = await invoke("get_vote", { key: forKey });
    if (forKey === key && (vote || 0) !== (game.entry.vndb_vote || 0)) {
      game.entry.vndb_vote = vote || 0;
      renderVote(game.entry);
    }
    part("vote-state").textContent = "";
  } catch (error) {
    part("vote-state").textContent = String(error);
  }
}

async function saveVote() {
  const vote = Number(part("vote").value) || null;
  part("vote").disabled = true;
  part("vote-state").textContent = "Saving…";
  try {
    await invoke("set_vote", { key, vote });
    game.entry.vndb_vote = vote || 0;
    part("vote-state").textContent = "Saved on VNDB ✓";
  } catch (error) {
    part("vote-state").textContent = String(error);
    renderVote(game.entry);
  }
  part("vote").disabled = false;
}

function renderLauncher(entry) {
  const launcher = entry.launcher in LAUNCHERS ? entry.launcher : "";

  segmented(part("launcher"), launcher, async (value) => {
    if (value && !toolIsSet(value) && !(await locateTool(value))) {
      return;
    }
    await call("update_game", { key, fields: { launcher: value } });
  });

  if (!launcher) {
    part("launcher-note").textContent =
      "For Japanese VNs with garbled text or that won't start: Play can go through Locale Emulator or NTLEA.";
  } else if (game.tool) {
    part("launcher-note").textContent = `Play starts it through ${game.tool}.`;
  } else {
    part("launcher-note").textContent =
      `${LAUNCHERS[launcher].exe} can't be found anymore — Play will ask where it is.`;
  }
}

function toolIsSet(launcher) {
  const path = launcher === "le" ? store.settings.locale_emulator_path : store.settings.ntlea_path;
  return !!path;
}

function daySeconds(day) {
  return (game.entry.daily || {})[isoDay(day)] || 0;
}

function renderStats(entry) {
  const today = midnight(new Date());
  const monday = addDays(today, -((today.getDay() + 6) % 7));
  let week = 0;
  for (let day = monday; day <= today; day = addDays(day, 1)) {
    week += daySeconds(day);
  }

  part("total").textContent = formatPlaytime(entry.playtime_seconds || 0);
  part("week").textContent = formatPlaytime(week);
  part("sessions").textContent = entry.sessions || "—";
  part("last").textContent = lastPlayed(entry.last_played) || "—";
}

function dailyPoints(today) {
  const points = [];
  for (let back = 29; back >= 0; back--) {
    const day = addDays(today, -back);
    points.push({ day, seconds: daySeconds(day), tip: `${weekday(day)} ${shortDate(day, today)}` });
  }
  return points;
}

function weeklyPoints(today) {
  const thisMonday = addDays(today, -((today.getDay() + 6) % 7));
  const points = [];
  for (let back = 11; back >= 0; back--) {
    const monday = addDays(thisMonday, -7 * back);
    let seconds = 0;
    for (let i = 0; i < 7; i++) {
      const day = addDays(monday, i);
      if (day <= today) {
        seconds += daySeconds(day);
      }
    }
    points.push({ day: monday, seconds, tip: `Week of ${shortDate(monday, today)}` });
  }
  return points;
}

function renderChart() {
  segmented(part("range"), range, (value) => {
    range = value;
    renderChart();
  });

  const today = midnight(new Date());
  const points = range === "weeks" ? weeklyPoints(today) : dailyPoints(today);

  const every = range === "weeks" ? 3 : 7;
  for (const [i, point] of points.entries()) {
    point.axis = (points.length - 1 - i) % every === 0 ? shortDate(point.day, today) : "";
  }
  drawChart(part("chart"), points);

  const days = Object.keys(game.entry.daily || {}).sort();
  part("history-note").textContent = days.length
    ? `History since ${shortDate(parseDay(days[0]), today)}. Time read before that only counts in the total.`
    : "History fills in as you read — time read before it was tracked only counts in the total.";
}

function openEditor() {
  const seconds = game.entry.playtime_seconds || 0;
  part("hours").value = Math.floor(seconds / 3600);
  part("minutes").value = Math.floor((seconds % 3600) / 60);
  part("editor").hidden = false;
  part("edit-total").hidden = true;
  part("hours").select();
}

function closeEditor() {
  part("editor").hidden = true;
  part("edit-total").hidden = false;
}

async function saveTotal(event) {
  event.preventDefault();
  const hours = Number(part("hours").value || 0);
  const minutes = Number(part("minutes").value || 0);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours < 0 || minutes < 0) {
    toast("Enter whole numbers of hours and minutes.", { error: true });
    return;
  }
  await call("set_playtime", { key, seconds: hours * 3600 + minutes * 60 });
  closeEditor();
  setTimeout(load, 400);
}

async function renderShots() {
  const strip = part("shots");
  part("shot-count").textContent = game.shot_count ? String(game.shot_count) : "";
  part("all-shots").hidden = !game.shot_count;

  const hotkey = game.hotkey;
  part("shots-hint").hidden = game.shot_count > 0;
  part("shots-hint").textContent = hotkey
    ? `Press ${hotkey} while reading to capture the game's window.`
    : "Pick a screenshot key in Settings to capture the game's window.";

  strip.replaceChildren();
  for (const path of game.shots) {
    const img = el("img", { alt: "" });
    strip.append(
      el(
        "button",
        { onclick: () => show("screenshots", { key, select: path, back: "game" }) },
        img,
      ),
    );
    invoke("thumbnail", { path, width: 320, height: 180 }).then(
      (thumb) => (img.src = fileUrl(thumb)),
    );
  }
}

register({
  id: "game",
  nav: "library",
  build,
  show: showPage,
  onKey: (event) => event.key === "Escape" && show("library"),
});
