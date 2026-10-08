const BASE = {
  dark: {
    label: "Dark",
    mode: "dark",
    BG: "#111214",
    SURFACE: "#1B1C20",
    SURFACE_ALT: "#24262B",
    SURFACE_HOVER: "#2E3036",
    BORDER: "#2B2D33",
    TEXT: "#F2F3F5",
    MUTED: "#A3A7B0",
    SUBTLE: "#6F737C",
    ACCENT: "#5865F2",
    ACCENT_HOVER: "#4752C4",
    ACCENT_SOFT: "#2A2D52",
    ON_ACCENT: "#FFFFFF",
    SELECTED: "#5865F2",
    SELECTED_HOVER: "#4752C4",
    GREEN: "#23A55A",
    RED: "#F23F43",
    DANGER_HOVER: "#3A1F22",
    DANGER_BORDER: "#5A2A2E",
    YELLOW: "#F0B232",
    YELLOW_SOFT: "#3A3120",
    PLACEHOLDER_TOP: "#2B2D42",
    PLACEHOLDER_BOTTOM: "#1C1D24",
    PLACEHOLDER_FG: "#6E748C",
  },
  light: {
    label: "Light",
    mode: "light",
    BG: "#F2F3F5",
    SURFACE: "#FFFFFF",
    SURFACE_ALT: "#E8E9ED",
    SURFACE_HOVER: "#DCDEE3",
    BORDER: "#D6D8DD",
    TEXT: "#1E1F22",
    MUTED: "#5C5F66",
    SUBTLE: "#80848E",
    ACCENT: "#5865F2",
    ACCENT_HOVER: "#4752C4",
    ACCENT_SOFT: "#E3E5FD",
    ON_ACCENT: "#FFFFFF",
    SELECTED: "#B7BDF9",
    SELECTED_HOVER: "#A5ACF5",
    GREEN: "#1A7F45",
    RED: "#D92D35",
    DANGER_HOVER: "#FBE1E2",
    DANGER_BORDER: "#F3B8BA",
    YELLOW: "#9A6A00",
    YELLOW_SOFT: "#FCF1D6",
    PLACEHOLDER_TOP: "#E3E5EC",
    PLACEHOLDER_BOTTOM: "#D3D6DE",
    PLACEHOLDER_FG: "#8A8FA0",
  },
  sakura: {
    label: "Sakura",
    mode: "light",
    BG: "#FFDCE8",
    SURFACE: "#FBE3EB",
    SURFACE_ALT: "#F6D3DF",
    SURFACE_HOVER: "#EFC3D3",
    BORDER: "#EFC3D3",
    TEXT: "#3A2230",
    MUTED: "#7B5566",
    SUBTLE: "#A07A8B",
    ACCENT: "#C73E72",
    ACCENT_HOVER: "#A8305E",
    ACCENT_SOFT: "#F5C2D5",
    ON_ACCENT: "#FFFFFF",
    SELECTED: "#EC94B5",
    SELECTED_HOVER: "#E3809F",
    GREEN: "#17703F",
    RED: "#C8283E",
    DANGER_HOVER: "#F9CFD6",
    DANGER_BORDER: "#EBA5B3",
    YELLOW: "#8A5E00",
    YELLOW_SOFT: "#FBE7C8",
    PLACEHOLDER_TOP: "#F6CFDC",
    PLACEHOLDER_BOTTOM: "#EDBBCD",
    PLACEHOLDER_FG: "#B0788E",
  },
};

export function normalizeHex(value) {
  let text = String(value || "")
    .trim()
    .replace(/^#/, "");
  if (text.length === 3) text = [...text].map((c) => c + c).join("");
  return /^[0-9a-f]{6}$/i.test(text) ? "#" + text.toUpperCase() : null;
}

const rgb = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));

export function mix(a, b, amount) {
  const [x, y] = [rgb(a), rgb(b)];
  return (
    "#" +
    x
      .map((v, i) =>
        Math.round(v + (y[i] - v) * amount)
          .toString(16)
          .padStart(2, "0")
          .toUpperCase(),
      )
      .join("")
  );
}

function contrast(a, b) {
  const lum = (c) => {
    const lin = rgb(c)
      .map((v) => v / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  };
  const [hi, lo] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (hi + 0.05) / (lo + 0.05);
}

export function buildCustomPalette(custom = {}) {
  const mode = custom.mode === "light" ? "light" : "dark";
  const base = BASE[mode];
  const pick = (k) => normalizeHex(custom[k]) || base[k];
  const [bg, surface, accent, text] = ["BG", "SURFACE", "ACCENT", "TEXT"].map(pick);
  const alt = mix(surface, text, 0.07);
  let selected = accent;
  for (let step = 0; step < 29; step++) {
    selected = mix(alt, accent, 1 - step * 0.035);
    if (contrast(text, selected) >= 4.5) break;
  }
  const onAccent =
    contrast("#FFFFFF", accent) >= contrast("#111111", accent) ? "#FFFFFF" : "#111111";
  const palette = {
    ...base,
    label: "Custom",
    mode,
    BG: bg,
    SURFACE: surface,
    SURFACE_ALT: alt,
    SURFACE_HOVER: mix(surface, text, 0.13),
    BORDER: mix(surface, text, 0.12),
    TEXT: text,
    MUTED: mix(text, surface, 0.3),
    SUBTLE: mix(text, surface, 0.55),
    ACCENT: accent,
    ACCENT_HOVER: mix(accent, "#000000", 0.18),
    ACCENT_SOFT: mix(surface, accent, 0.22),
    ON_ACCENT: onAccent,
    SELECTED: selected,
    SELECTED_HOVER: mix(selected, text, 0.1),
    DANGER_HOVER: mix(surface, base.RED, 0.15),
    DANGER_BORDER: mix(surface, base.RED, 0.45),
    YELLOW_SOFT: mix(surface, base.YELLOW, 0.2),
    PLACEHOLDER_TOP: mix(surface, accent, 0.14),
    PLACEHOLDER_BOTTOM: mix(surface, text, 0.08),
    PLACEHOLDER_FG: mix(text, surface, 0.5),
  };
  for (const [token, value] of Object.entries(custom.overrides || {})) {
    const color = normalizeHex(value);
    if (color && token in base) palette[token] = color;
  }
  return palette;
}

const preset = (label, mode, BG, SURFACE, ACCENT, TEXT, overrides = {}) => ({
  ...buildCustomPalette({ mode, BG, SURFACE, ACCENT, TEXT, overrides }),
  label,
});

export const THEMES = {
  ...BASE,
  butter: preset("Butter", "light", "#FFF1C7", "#FFF8E1", "#E0661A", "#4A2A12"),
  lilac: preset("Lilac", "light", "#CBCFF4", "#FFF9DC", "#5B5FC7", "#2F2C57"),
  sky: preset("Sky", "light", "#69D0F1", "#EFEDD1", "#15729A", "#16323F"),
  mint: preset("Neon Mint", "dark", "#101516", "#182122", "#54E6D4", "#E6F7F4"),
  amoled: preset("AMOLED Black", "dark", "#000000", "#0E0F11", "#5865F2", "#F2F3F5"),
  dracula: preset("Dracula", "dark", "#282A36", "#343746", "#BD93F9", "#F8F8F2"),
  nord: preset("Nord", "dark", "#2E3440", "#3B4252", "#88C0D0", "#ECEFF4"),
  mocha: preset("Catppuccin Mocha", "dark", "#1E1E2E", "#313244", "#CBA6F7", "#CDD6F4"),
  tokyo: preset("Tokyo Night", "dark", "#1A1B26", "#24283B", "#7AA2F7", "#C0CAF5"),
  gruvbox: preset("Gruvbox", "dark", "#282828", "#3C3836", "#FABD2F", "#EBDBB2"),
  rosepine: preset("Rosé Pine", "dark", "#191724", "#1F1D2E", "#EBBCBA", "#E0DEF4"),
  latte: preset("Catppuccin Latte", "light", "#DCE0E8", "#EFF1F5", "#8839EF", "#4C4F69", {
    MUTED: "#5C5F77",
  }),
  solarized: preset("Solarized Light", "light", "#EEE8D5", "#FDF6E3", "#268BD2", "#073642"),
};

export function resolveTheme(name, custom) {
  if (name === "custom") return buildCustomPalette(custom);
  if (name === "system")
    return THEMES[matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"];
  return THEMES[name] || THEMES.dark;
}

export function applyPalette(palette) {
  const root = document.documentElement.style;
  for (const [k, v] of Object.entries(palette)) {
    if (k === k.toUpperCase()) root.setProperty("--" + k.toLowerCase().replaceAll("_", "-"), v);
  }
  document.documentElement.dataset.mode = palette.mode;
}
