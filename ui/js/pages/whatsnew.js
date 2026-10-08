import { $, el, html } from "../dom.js";
import { invoke } from "../tauri.js";
import { register, show } from "../router.js";
import { store } from "../store.js";
import { call } from "../ui.js";
import { clean, pick, renderMarkdown } from "../components/release-notes.js";
import { RELEASES_PAGE, bugReportUrl, suggestionUrl } from "../links.js";
import { discordButton } from "../components/discord-button.js";

const TEMPLATE = `
  <div class="page-head">
    <h2>What's new</h2>
    <div class="row">
      <button class="link" data-id="github">All releases on GitHub</button>
      <button class="btn" data-id="done">Got it</button>
    </div>
  </div>
  <div class="muted" data-id="sub"></div>

  <div class="card community">
    <div>
      <b>Found a bug, or have an idea?</b>
      <div class="muted small-text">
        Tell me on GitHub (your version is filled in for you), or come say hi on Discord.
      </div>
    </div>
    <div class="row">
      <button class="btn secondary" data-id="bug">Report a bug</button>
      <button class="btn secondary" data-id="idea">Suggest something</button>
      <span data-id="discord-slot"></span>
    </div>
  </div>

  <div class="card notes" data-id="notes"></div>
`;

let root;
let loading = 0;

const part = (id) => $(`[data-id="${id}"]`, root);

function build(container) {
  root = container;
  root.append(html(TEMPLATE));
  part("github").onclick = () => call("open_url", { url: RELEASES_PAGE });
  part("done").onclick = () => show("home");

  part("bug").onclick = () => call("open_url", { url: bugReportUrl(store.version) });
  part("idea").onclick = () => call("open_url", { url: suggestionUrl(store.version) });
  part("discord-slot").append(discordButton());
}

async function showPage({ since = null, recent = 0 } = {}) {
  const job = ++loading;
  const version = store.version;
  part("sub").textContent = "Loading the release notes…";
  part("notes").replaceChildren();
  part("notes").hidden = true;

  let notes;
  try {
    notes = pick(await invoke("release_notes"), version, { since, recent });
  } catch {
    if (job === loading) {
      part("sub").textContent =
        "Couldn't load the release notes (are you offline?). They're on GitHub too: “All releases on GitHub”.";
    }
    return;
  }
  if (job !== loading) {
    return;
  }

  if (!notes.length) {
    part("sub").textContent = `You're on version ${version}. No release notes were found for it.`;
    return;
  }
  if (since && notes.length > 1) {
    part("sub").textContent =
      `Updated from ${since} to ${version}. Here's everything that changed.`;
  } else if (since || notes.length === 1) {
    part("sub").textContent = `You're now on version ${version}.`;
  } else {
    part("sub").textContent = `You're on version ${version}. The latest releases:`;
  }

  const blocks = notes.flatMap((note, i) => {
    const body = clean(note.body, note.version);
    return [
      i > 0 && el("hr"),
      el("div", { class: "version" }, `Version ${note.version}`),
      note.date && el("div", { class: "date" }, note.date),
      ...(body ? renderMarkdown(body) : [el("p", { class: "muted" }, "No details for this one.")]),
    ];
  });
  part("notes").replaceChildren(...blocks.filter(Boolean));
  part("notes").hidden = false;
}

register({
  id: "whatsnew",
  nav: "settings",
  build,
  show: showPage,
  onKey: (event) => event.key === "Escape" && show("home"),
});
