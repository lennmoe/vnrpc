import { invoke, listen } from "../tauri.js";
import { applyPalette, resolveTheme } from "../themes.js";

function apply(settings) {
  applyPalette(resolveTheme(settings.theme || "system", settings.custom_theme));
}

export async function followTheme() {
  const state = await invoke("get_state");
  apply(state.settings);
  await listen("settings-changed", (event) => apply(event.payload));
}
