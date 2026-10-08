import { $, el, html } from "../dom.js";
import { invoke, pickFile, pickFolder, pickSaveFile } from "../tauri.js";
import { register, show } from "../router.js";
import { store, subscribe, update } from "../store.js";
import { ask, call, toast, toggle } from "../ui.js";
import { hotkeyInput } from "../components/hotkey-input.js";
import { renderThemeTab } from "../components/theme-tab.js";
import { offerUpdate } from "../components/update.js";
import { discordButton } from "../components/discord-button.js";

const TEMPLATE = `
  <div class="page-head">
    <h2>Settings</h2>
    <div data-id="discord-slot"></div>
  </div>

  <div class="card">
    <div class="tabs" data-id="tabs">
      <button data-tab="general">General</button>
      <button data-tab="theme">Theme</button>
      <button data-tab="rules">Title rules</button>
      <button data-tab="blacklist">Never detect</button>
    </div>
    <div class="settings-body" data-id="body" style="padding-top: 16px"></div>
  </div>

  <div class="settings-footer">
    <span class="muted" data-id="version"></span>
    <div class="row">
      <button class="btn secondary small" data-id="check-update">Check for updates</button>
    </div>
  </div>
`;

let root;
let tab = "general";

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));

  for (const button of part("tabs").querySelectorAll("button")) {
    button.onclick = () => {
      tab = button.dataset.tab;
      render();
    };
  }

  buildFooter();

  subscribe("settings", () => {
    const typing =
      root.contains(document.activeElement) && document.activeElement.matches("input, textarea");
    if (root.classList.contains("active") && !typing) {
      render();
    }
  });
}

function showPage(params = {}) {
  if (params.tab) {
    tab = params.tab;
  }
  render();
}

function buildFooter() {
  part("version").textContent = `Visual Novel RPC ${store.version}`;

  const check = part("check-update");
  check.onclick = async () => {
    check.disabled = true;
    check.textContent = "Checking…";
    await offerUpdate({ quiet: false });
    check.disabled = false;
    check.textContent = "Check for updates";
  };

  part("discord-slot").append(discordButton());
}

async function save(changes) {
  update("settings", { ...store.settings, ...changes });
  await call("update_settings", { changes });
}

function render() {
  for (const button of part("tabs").querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.tab === tab);
  }

  const body = part("body");
  if (tab === "theme") {
    renderThemeTab(body, save);
  } else if (tab === "rules") {
    body.replaceChildren(...rulesTab());
  } else if (tab === "blacklist") {
    body.replaceChildren(...blacklistTab());
  } else {
    body.replaceChildren(...generalTab());
  }
}

const section = (title) => el("div", { class: "section-title" }, title);

const hint = (text) => el("div", { class: "hint-text" }, text);

function setting(key, label, hintText = "") {
  return toggle(label, store.settings[key], (on) => save({ [key]: on }), hintText);
}

function numberField(key, label, { min, max, fallback }) {
  const input = el("input", { type: "number", min, max, value: store.settings[key] ?? fallback });
  input.onchange = () => {
    const value = Math.min(max, Math.max(min, Math.round(Number(input.value) || fallback)));
    input.value = value;
    save({ [key]: value });
  };
  return el("div", { class: "field" }, el("span", {}, label), input);
}

function textField(key, { placeholder = "", type = "text" } = {}) {
  const input = el("input", { type, class: "wide", placeholder, value: store.settings[key] || "" });
  input.onchange = () => save({ [key]: input.value.trim() });
  return input;
}

function pathRow(key, { title, filters, folder = false, placeholder = "Not set" }) {
  const input = textField(key, { placeholder });

  const browse = el("button", { class: "btn secondary" }, "Browse…");
  browse.onclick = async () => {
    const options = { title, filters, defaultPath: input.value || undefined };
    const path = folder ? await pickFolder(options) : await pickFile(options);
    if (path) {
      input.value = path;
      save({ [key]: path });
    }
  };

  return el("div", { class: "row" }, input, browse);
}

function testedField(input, test) {
  const result = el("div", { class: "hint-text" });
  const button = el("button", { class: "btn secondary" }, "Test");

  button.onclick = async () => {
    result.className = "hint-text";
    result.textContent = "Testing…";
    try {
      const message = await test(input.value.trim());
      result.className = "hint-text ok-text";
      result.textContent = message;
    } catch (error) {
      result.className = "hint-text error-text";
      result.textContent = `Failed: ${error}`;
    }
  };

  return [el("div", { class: "row" }, input, button), result];
}

function generalTab() {
  return [
    ...discordSection(),
    ...presenceSection(),
    ...coversSection(),
    ...vndbSection(),
    ...screenshotsSection(),
    ...localeSection(),
    ...appSection(),
    ...mascotSection(),
    ...dataSection(),
    ...advancedSection(),
  ];
}

function discordSection() {
  const clientId = textField("discord_client_id");
  const test = async (id) => {
    await invoke("test_discord", { clientId: id });
    return "Connected — this ID works.";
  };

  return [
    section("Discord"),
    el("div", { class: "field-label" }, "Application ID"),
    ...testedField(clientId, test),
    hint(
      "Create one at discord.com/developers → New Application, then paste its Application ID. " +
        "No bot or OAuth needed.",
    ),
  ];
}

function presenceSection() {
  return [
    section("Presence"),
    setting("show_section", "Show where you are in the story", "The “Reading・Chapter 1” line."),
    setting("show_total_read", "Show total time read", "The “Total read: 3h 40m” line."),
    setting("show_elapsed", "Show elapsed time"),
    setting("clear_on_close", "Clear presence when the VN closes"),
    setting("show_vndb_button", "Add a “View on VNDB” button"),
    setting(
      "idle_when_unfocused",
      "Go idle when the VN isn't the active window",
      "Clears your Discord status and stops the elapsed time and the time read until you go back to the game.",
    ),
    numberField("idle_seconds", "Seconds in the background before going idle", {
      min: 0,
      max: 3600,
      fallback: 60,
    }),
  ];
}

function coversSection() {
  return [
    section("Covers & matching"),
    setting(
      "allow_nsfw_covers",
      "Allow NSFW-flagged covers",
      "Off: flagged covers are blurred here and replaced by the fallback image on Discord.",
    ),
    setting(
      "use_steam_names",
      "Use Steam library names",
      "Gives much better VNDB matches for games installed through Steam.",
    ),
  ];
}

function vndbSection() {
  const token = textField("vndb_token", { type: "password" });
  const test = async (value) => {
    if (!value) {
      throw "Paste a token first.";
    }
    const name = await invoke("check_vndb_token", { token: value });
    return `Connected as ${name}.`;
  };

  return [
    section("VNDB list"),
    el("div", { class: "field-label" }, "Personal token"),
    ...testedField(token, test),
    hint(
      "vndb.org → your profile → Edit → Applications → New token, with access to your list and " +
        "permission to edit it.",
    ),
    setting(
      "vndb_sync",
      "Sync reading status to my VNDB list",
      "VNs you start are marked Playing, and statuses set in the Library are sent too. " +
        "Only VNs whose VNDB entry you picked or confirmed are synced.",
    ),
  ];
}

function screenshotsSection() {
  const key = hotkeyInput(store.settings.screenshot_hotkey, (value) =>
    save({ screenshot_hotkey: value }),
  );

  const volume = el("input", {
    type: "range",
    min: 0,
    max: 100,
    step: 5,
    value: store.settings.screenshot_volume ?? 30,
  });
  const volumeLabel = el("span", { class: "muted", style: { width: "44px", textAlign: "right" } });
  const showVolume = () =>
    (volumeLabel.textContent = Number(volume.value) ? `${volume.value}%` : "Off");
  volume.oninput = showVolume;
  volume.onchange = () => save({ screenshot_volume: Number(volume.value) });
  showVolume();

  const listen = el("button", { class: "btn secondary small", title: "Listen" }, "▶");
  listen.onclick = () => invoke("play_shutter", { volume: Number(volume.value) });

  return [
    section("Screenshots"),
    el("div", { class: "field" }, el("span", {}, "Capture key"), key),
    hint(
      "Click, then press the key or combination (Esc cancels, Backspace turns it off). It only works " +
        "while the game's window is in front, so other programs keep the key.",
    ),
    el(
      "div",
      { class: "field" },
      el("span", {}, "Capture sound"),
      el("div", { class: "row" }, volume, volumeLabel, listen),
    ),
    el("div", { class: "field-label" }, "Folder"),
    pathRow("screenshot_dir", {
      title: "Screenshot folder",
      folder: true,
      placeholder: store.defaultScreenshotRoot,
    }),
    hint("Each VN gets its own folder in there. Screenshots already taken aren't moved."),
  ];
}

function localeSection() {
  const exe = (name) => [{ name, extensions: ["exe"] }];
  return [
    section("Japanese locale"),
    hint(
      "For VNs that show garbled text or won't start: pick “Launch with” on a game's page in the " +
        "Library, and Play starts it through one of these.",
    ),
    el("div", { class: "field-label" }, "Locale Emulator  (LEProc.exe)"),
    pathRow("locale_emulator_path", { title: "Locate LEProc.exe", filters: exe("LEProc.exe") }),
    el("div", { class: "field-label" }, "NTLEA  (ntleas.exe)"),
    pathRow("ntlea_path", { title: "Locate ntleas.exe", filters: exe("ntleas.exe") }),
  ];
}

function appSection() {
  const autostart = toggle("Launch when Windows starts", store.autostart, async (on) => {
    await call("set_autostart", { enabled: on });
    store.autostart = on;
  });

  const whatsNew = el("button", { class: "btn secondary" }, "What's new");
  whatsNew.onclick = () => show("whatsnew", { recent: 5 });

  return [
    section("App"),
    setting("start_minimized", "Start minimized to the tray"),
    autostart,
    setting(
      "check_updates",
      "Check for updates at launch",
      `Version ${store.version}. New GitHub releases are offered when the app starts.`,
    ),
    el(
      "div",
      { class: "row" },
      whatsNew,
      el(
        "span",
        { class: "muted small-text" },
        `Version ${store.version}: the notes of the last few releases.`,
      ),
    ),
  ];
}

function mascotSection() {
  const backToCorner = el("button", { class: "btn secondary" }, "Put it back in the corner");
  backToCorner.onclick = () => save({ mascot_pos: null });

  return [
    section("Desktop mascot"),
    setting(
      "mascot_enabled",
      "Show a desktop mascot (ukagaka)",
      "A character standing on your desktop who comments on what you read. Drag it anywhere, click it, " +
        "double-click to open the app, right-click for more.",
    ),
    el(
      "div",
      { class: "field-label" },
      "Character image  (a PNG with a transparent background; empty = the built-in one)",
    ),
    pathRow("mascot_image", {
      title: "Character image",
      filters: [{ name: "Images", extensions: ["png", "webp", "gif"] }],
    }),
    numberField("mascot_height", "Height in pixels", { min: 80, max: 2000, fallback: 420 }),
    setting("mascot_talk", "Speech balloons"),
    setting(
      "mascot_topmost",
      "Keep it above other windows",
      "Off: it stays on the desktop, behind your windows.",
    ),
    el("div", { class: "row" }, backToCorner),
  ];
}

function dataSection() {
  const exportButton = el("button", { class: "btn secondary", onclick: exportData }, "Export…");
  const importButton = el("button", { class: "btn secondary", onclick: importData }, "Import…");

  return [
    section("Your data"),
    hint(
      "Settings, the Library (time read, history, statuses) and custom covers in one file, to move to " +
        "another PC or keep a copy. It includes your VNDB token: don't share it.",
    ),
    el("div", { class: "row" }, exportButton, importButton),
  ];
}

async function exportData() {
  const path = await pickSaveFile({
    title: "Export data",
    defaultPath: await invoke("backup_default_name"),
    filters: [{ name: "Visual Novel RPC backup", extensions: ["zip"] }],
  });
  if (!path) {
    return;
  }
  const count = await call("export_data", { path });
  toast(`Saved ${count} VN${count === 1 ? "" : "s"} and your settings`);
}

async function importData() {
  const path = await pickFile({
    title: "Import data",
    filters: [{ name: "Visual Novel RPC backup", extensions: ["zip"] }],
  });
  if (!path) {
    return;
  }

  const folder = await invoke("backup_folder");
  const sure = await ask(
    "Import data",
    `Replace your settings and Library with the ones in this file? What you have now is saved first in ${folder}.`,
    { yes: "Replace", danger: true },
  );
  if (!sure) {
    return;
  }

  const count = await call("import_data", { path });
  toast(`Loaded ${count} VN${count === 1 ? "" : "s"} and the settings`);
}

function advancedSection() {
  return [
    section("Advanced"),
    numberField("update_min_interval", "Min. seconds between presence updates", {
      min: 1,
      max: 300,
      fallback: 5,
    }),
    el("div", { class: "field-label" }, "Fallback Discord asset key"),
    textField("default_asset_key"),
    hint(
      "The image Discord shows when the cover can't be: a local file, an NSFW cover, or no cover.",
    ),
  ];
}

function checkPattern(pattern) {
  new RegExp(pattern.replace(/\(\?P</g, "(?<"), "iu");
}

function rulesTab() {
  const lines = (store.settings.title_rules || []).map((rule) => JSON.stringify(rule));
  const text = el("textarea", { spellcheck: "false" });
  text.value = lines.join("\n");

  const error = el("div", { class: "hint-text error-text" });
  const saveButton = el("button", { class: "btn" }, "Save rules");

  saveButton.onclick = async () => {
    const rules = [];
    const all = text.value.split("\n");
    for (const [i, raw] of all.entries()) {
      const line = raw.trim();
      if (!line) {
        continue;
      }
      try {
        const rule = JSON.parse(line);
        if (typeof rule !== "object" || typeof rule.pattern !== "string") {
          throw new Error('each rule must be an object with a "pattern" string');
        }
        checkPattern(rule.pattern);
        rules.push(rule);
      } catch (problem) {
        error.textContent = `Line ${i + 1}: ${problem.message}`;
        return;
      }
    }
    error.textContent = "";
    await save({ title_rules: rules });
    toast("Title rules saved");
  };

  const example =
    '{"name": "part", "pattern": "part\\\\s*(?P<n>\\\\d+)", "label": "Part {n}", "section_type": "chapter"}';

  return [
    hint(
      "Extra rules run before the built-in ones. One JSON object per line; the first rule whose pattern " +
        "matches the window title wins.",
    ),
    el(
      "div",
      { class: "process-name", style: { display: "block", margin: "6px 0 10px" } },
      example,
    ),
    text,
    error,
    el("div", { class: "row end" }, saveButton),
  ];
}

function blacklistTab() {
  const list = store.settings.blacklist_exe || [];

  const chips = list.length
    ? list.map((exe) =>
        el(
          "span",
          { class: "chip" },
          exe,
          el(
            "button",
            {
              title: "Detect it again",
              onclick: () => save({ blacklist_exe: list.filter((x) => x !== exe) }),
            },
            "×",
          ),
        ),
      )
    : [el("span", { class: "muted" }, "Nothing yet.")];

  const input = el("input", { type: "text", class: "wide", placeholder: "osu!.exe" });
  const add = () => {
    let name = input.value.trim().split(/[\\/]/).pop();
    if (!name) {
      return;
    }
    if (!name.toLowerCase().endsWith(".exe")) {
      name += ".exe";
    }
    if (!list.some((x) => x.toLowerCase() === name.toLowerCase())) {
      save({ blacklist_exe: [...list, name] });
    }
    input.value = "";
  };
  input.onkeydown = (event) => event.key === "Enter" && add();

  return [
    hint(
      "Programs that are never detected as a visual novel. Their games are also hidden from the Library. " +
        "Browsers, Discord, Steam, OBS… are always ignored.",
    ),
    el("div", { class: "chips", style: { margin: "8px 0 14px" } }, chips),
    el("div", { class: "row" }, input, el("button", { class: "btn", onclick: add }, "Add")),
  ];
}

register({ id: "settings", build, show: showPage });
