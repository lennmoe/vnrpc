import { $, el, html } from "../dom.js";
import { formatPlaytime } from "../format.js";
import { fileUrl } from "../tauri.js";
import { register, show } from "../router.js";
import { store, subscribe } from "../store.js";
import { call, confirmButton, segmented, setCover, toast } from "../ui.js";

const TEMPLATE = `
  <div class="banner warn" data-id="paused" hidden>
    <i></i>Presence paused — nothing is being shared on Discord.
  </div>
  <div class="banner info" data-id="idle" hidden>
    <i></i>The VN is in the background: Discord is cleared and the timers are stopped.
  </div>

  <div class="card now" data-id="card">
    <div class="backdrop" data-id="backdrop"></div>

    <div class="now-main">
      <div class="cover big" data-id="cover"></div>

      <div class="now-info">
        <div class="eyebrow">Now reading</div>
        <h1 data-id="title"></h1>
        <div class="muted" data-id="sub"></div>

        <div class="chips">
          <span class="chip accent" data-id="section" hidden></span>
          <span class="chip" data-id="time"></span>
        </div>

        <div class="row">
          <button class="btn secondary" data-id="change-cover">Change cover…</button>
          <button class="btn secondary" data-id="vndb" hidden>VNDB page ↗</button>
          <button class="btn secondary" data-id="open-game">Library page</button>
        </div>
      </div>
    </div>

    <div class="discord">
      <div class="discord-head">
        <span class="label">Discord preview</span>
        <span class="subtle">what your friends see</span>
      </div>
      <div data-id="activity"></div>
    </div>
  </div>

  <div class="card empty" data-id="empty">
    <img src="assets/mascot.png" alt="" class="mascot" />
    <div>
      <div class="eyebrow">Waiting for a visual novel</div>
      <h1>Start a VN and it shows up here</h1>
      <p class="muted">
        Most engines (Ren'Py, KiriKiri, SiglusEngine, Unity…) are found by themselves.
        If yours isn't, switch Detection to Manual and pick its window.
      </p>
    </div>
  </div>

  <div class="card detection">
    <b>Detection</b>
    <div class="seg" data-id="mode">
      <button data-v="auto">Auto</button>
      <button data-v="manual">Manual</button>
    </div>
    <span class="muted" data-id="mode-hint"></span>
    <select data-id="window" hidden></select>
    <button class="btn secondary small" data-id="refresh" hidden>Refresh</button>

    <div class="detected-process" data-id="process" hidden>
      <span class="muted small-text">Detected</span>
      <span class="process-name" data-id="process-name"></span>
      <button class="btn danger small" data-id="not-vn">Not a VN</button>
    </div>
  </div>

  <div class="status-line" data-id="status"></div>
`;

let root;
const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  part("change-cover").onclick = () => show("cover", { key: store.snapshot.key });
  part("open-game").onclick = () => show("game", { key: store.snapshot.key });
  part("refresh").onclick = fillWindows;
  part("window").onchange = (event) => {
    const changes = { manual_target: { exe: event.target.value, title_contains: "" } };
    call("update_settings", { changes });
  };

  subscribe("snapshot", renderSnapshot);
  subscribe("status", renderStatus);
  subscribe("settings", renderDetection);

  renderSnapshot(store.snapshot);
  renderStatus(store.status);
  renderDetection();
}

function renderSnapshot(snap) {
  const detected = !!snap.detected;

  part("card").hidden = !detected;
  part("empty").hidden = detected;
  part("paused").hidden = !snap.paused;
  part("idle").hidden = !(detected && snap.idle && !snap.paused);
  renderProcess(snap);

  if (!detected) {
    return;
  }

  part("title").textContent = snap.game_name || snap.raw_title;
  part("sub").textContent = [snap.engine_name, snap.exe].filter(Boolean).join("  ·  ");
  part("section").hidden = !snap.section_label;
  part("section").textContent = snap.section_label;
  part("time").textContent = `${formatPlaytime(snap.playtime_seconds)} read`;

  const cover = snap.cover || {};
  setCover(part("cover"), { path: cover.local_path, nsfw: cover.nsfw, label: snap.game_name });

  const hidden = cover.nsfw && !store.settings.allow_nsfw_covers;
  const backdrop = cover.local_path && !hidden ? `url("${fileUrl(cover.local_path)}")` : "none";
  part("backdrop").style.backgroundImage = backdrop;

  const vn = snap.vn;
  part("vndb").hidden = !vn;
  part("vndb").onclick = () => call("open_url", { url: `https://vndb.org/${vn.id}` });

  renderActivity(snap);
}

function renderProcess(snap) {
  part("process").hidden = !snap.detected;
  if (!snap.detected) {
    return;
  }

  part("process-name").textContent = snap.exe;
  confirmButton(part("not-vn"), "Not a VN", async () => {
    await call("not_a_vn", { exe: snap.exe });
    toast(`${snap.exe} won't be detected again`);
  });
}

function whyNothingShared(snap) {
  if (snap.paused) {
    return "Paused: nothing is shared.";
  }
  if (snap.idle) {
    return "Idle: nothing is shared until the VN is back in front.";
  }
  if (snap.privacy === "off") {
    return "This VN is set to share nothing on Discord.";
  }
  return "Nothing is shared.";
}

function renderActivity(snap) {
  const box = part("activity");
  const activity = snap.activity;

  if (!activity) {
    box.replaceChildren(el("div", { class: "muted" }, whyNothingShared(snap)));
    return;
  }

  const cover = snap.cover || {};
  const showsCover = activity.large_image && activity.large_image === cover.discord_image;
  const picture = el("div", { class: "cover thumb" });
  setCover(picture, { path: showsCover ? cover.local_path : "", label: activity.name });

  const buttons = (activity.buttons || []).map(([label, url]) =>
    el("button", { class: "btn secondary small", onclick: () => call("open_url", { url }) }, label),
  );

  const lines = el(
    "div",
    { class: "lines" },
    el("b", {}, activity.name),
    activity.details && el("span", { class: "muted" }, activity.details),
    activity.state && el("span", { class: "muted" }, activity.state),
    activity.start && el("span", { class: "elapsed", "data-start": activity.start }),
    buttons,
  );

  box.replaceChildren(el("div", { class: "activity" }, picture, lines));
  tickElapsed();
}

function tickElapsed() {
  const pad = (n) => String(n).padStart(2, "0");

  for (const node of document.querySelectorAll(".elapsed[data-start]")) {
    const seconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(node.dataset.start));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const clock = hours ? `${hours}:${pad(minutes)}` : `${minutes}`;
    node.textContent = `${clock}:${pad(seconds % 60)} elapsed`;
  }
}

setInterval(tickElapsed, 1000);

function renderStatus(status) {
  const lines = [status.vndb_msg, `Discord: ${status.discord_msg || "connecting…"}`];
  part("status").textContent = lines.filter(Boolean).join("   ·   ");
}

function renderDetection() {
  const mode = store.settings.detection_mode === "manual" ? "manual" : "auto";

  segmented(part("mode"), mode, (value) =>
    call("update_settings", { changes: { detection_mode: value } }),
  );
  part("mode-hint").textContent =
    mode === "auto" ? "Finds running VN engines by itself" : "Uses the window you pick";
  part("window").hidden = mode !== "manual";
  part("refresh").hidden = mode !== "manual";

  if (mode === "manual") {
    fillWindows();
  }
}

async function fillWindows() {
  const windows = await call("list_windows");
  const current = (store.settings.manual_target || {}).exe || "";
  const seen = new Set();
  const options = [el("option", { value: "" }, "Pick the game window…")];

  for (const win of windows) {
    const exe = win.exe_path.split("\\").pop();
    if (!exe || seen.has(exe.toLowerCase())) {
      continue;
    }
    seen.add(exe.toLowerCase());
    const selected = exe.toLowerCase() === current.toLowerCase();
    options.push(el("option", { value: exe, selected }, `${win.title}  —  ${exe}`));
  }

  if (current && !seen.has(current.toLowerCase())) {
    options.push(el("option", { value: current, selected: true }, `${current} (not running)`));
  }
  part("window").replaceChildren(...options);
}

register({ id: "home", build });
