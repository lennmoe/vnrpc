import { el } from "../dom.js";
import { invoke } from "../tauri.js";
import { store } from "../store.js";
import { openDialog, toast } from "../ui.js";

export async function offerUpdate({ quiet = true } = {}) {
  let release;
  try {
    release = await invoke("check_update");
  } catch {
    if (!quiet) {
      toast("Couldn't reach GitHub to check for updates (are you offline?).", { error: true });
    }
    return "failed";
  }

  if (!release) {
    if (!quiet) {
      toast(`You're up to date (version ${store.version}).`);
    }
    return "up-to-date";
  }

  const answer = await openDialog({
    title: "Update available",
    body: el(
      "p",
      { class: "muted" },
      `Visual Novel RPC ${release.version} is out (you have ${store.version}). Download it and restart now?`,
    ),
    actions: [
      { label: "Later", kind: "secondary", value: false },
      { label: "Update", value: true },
    ],
  });
  if (answer !== true) {
    return "update";
  }

  toast(`Downloading version ${release.version}…`);
  try {
    await invoke("install_update", { release });
  } catch (error) {
    toast(`Update failed: ${error}`, { error: true });
  }
  return "update";
}
