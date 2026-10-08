import { el } from "../dom.js";
import { THEMES, buildCustomPalette, resolveTheme, normalizeHex } from "../themes.js";
import { store } from "../store.js";
import { segmented } from "../ui.js";

const CUSTOM_KEYS = { BG: "Background", SURFACE: "Cards", ACCENT: "Accent", TEXT: "Text" };

function miniature(p) {
  const line = (color, width) =>
    el("div", { class: "mini-line", style: { background: color, width } });

  const buttons = el(
    "div",
    { class: "mini-buttons" },
    el("i", { style: { background: p.ACCENT, width: "46px" } }),
    el("i", {
      style: { background: p.SURFACE_ALT, width: "38px", border: `1px solid ${p.BORDER}` },
    }),
  );

  return el(
    "div",
    { class: "mini-card", style: { background: p.SURFACE, borderColor: p.BORDER } },
    line(p.TEXT, "70%"),
    line(p.MUTED, "48%"),
    buttons,
  );
}

function tile(name, label, palettes, selected, onPick) {
  let preview;
  if (palettes.length === 1) {
    preview = el(
      "div",
      { class: "mini", style: { background: palettes[0].BG } },
      miniature(palettes[0]),
    );
  } else {
    const half = (p) =>
      el(
        "div",
        { style: { flex: 1, background: p.BG, padding: "14px", display: "flex" } },
        miniature(p),
      );
    preview = el(
      "div",
      { class: "mini", style: { padding: 0, overflow: "hidden" } },
      half(palettes[0]),
      half(palettes[1]),
    );
  }

  return el(
    "button",
    { class: `theme-tile ${selected ? "on" : ""}`, onclick: () => onPick(name) },
    preview,
    el("span", { class: "name" }, label),
  );
}

export function renderThemeTab(container, save) {
  const current = store.settings.theme || "system";
  const custom = { mode: "dark", ...(store.settings.custom_theme || {}) };
  for (const key of Object.keys(CUSTOM_KEYS)) {
    custom[key] = normalizeHex(custom[key]) || THEMES.dark[key];
  }

  const pick = (name) => save({ theme: name });
  const names = Object.keys(THEMES);
  const dark = names.filter((n) => THEMES[n].mode === "dark");
  const light = names.filter((n) => THEMES[n].mode === "light");

  const group = (title, tiles) => [
    el("div", { class: "section-title" }, title),
    el("div", { class: "theme-group" }, tiles),
  ];

  const automatic = tile(
    "system",
    "Match Windows",
    [THEMES.dark, THEMES.light],
    current === "system",
    pick,
  );
  const customTile = tile(
    "custom",
    "Custom",
    [buildCustomPalette(custom)],
    current === "custom",
    () => save({ theme: "custom", custom_theme: custom }),
  );

  container.replaceChildren(
    el("p", { class: "muted small-text" }, "Click a theme to use it."),
    ...group("Automatic", [automatic]),
    ...group(
      "Dark",
      dark.map((n) => tile(n, THEMES[n].label, [THEMES[n]], current === n, pick)),
    ),
    ...group(
      "Light",
      light.map((n) => tile(n, THEMES[n].label, [THEMES[n]], current === n, pick)),
    ),
    el("div", { class: "section-title" }, "Your own"),
    el(
      "div",
      { class: "custom-editor" },
      el("div", { style: { width: "170px" } }, customTile),
      customEditor(custom, save),
    ),
  );
}

function customEditor(custom, save) {
  const draft = { ...custom };
  const preview = () => save({ theme: "custom", custom_theme: draft });

  const mode = el(
    "div",
    { class: "seg" },
    el("button", { "data-v": "dark" }, "Dark"),
    el("button", { "data-v": "light" }, "Light"),
  );
  const setMode = (value) => {
    draft.mode = value;
    segmented(mode, value, setMode);
  };
  segmented(mode, draft.mode, setMode);

  const colors = el(
    "div",
    { class: "custom-colors" },
    Object.entries(CUSTOM_KEYS).map(([key, label]) => {
      const input = el("input", { type: "color", value: draft[key].toLowerCase() });
      input.oninput = () => (draft[key] = input.value.toUpperCase());
      return el("label", {}, input, label);
    }),
  );

  const fromCurrent = () => {
    const palette = resolveTheme(store.settings.theme || "system", store.settings.custom_theme);
    for (const key of Object.keys(CUSTOM_KEYS)) {
      draft[key] = palette[key];
    }
    draft.mode = palette.mode;
    save({ theme: "custom", custom_theme: draft });
  };

  return el(
    "div",
    {},
    el("div", { class: "muted small-text" }, "Pick four colors; the rest is worked out from them."),
    el("div", { style: { margin: "10px 0" } }, mode),
    colors,
    el(
      "div",
      { class: "row" },
      el("button", { class: "btn", onclick: preview }, "Use my colors"),
      el(
        "button",
        { class: "btn secondary", onclick: fromCurrent },
        "Start from the current theme",
      ),
    ),
  );
}
