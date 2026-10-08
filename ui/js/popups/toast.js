import { el } from "../dom.js";
import { invoke, listen, fileUrl } from "../tauri.js";
import { followTheme } from "./theme.js";

const box = document.getElementById("toast");

function render(toast) {
  if (!toast) {
    return;
  }

  const picture = toast.image ? el("img", { src: fileUrl(toast.image), alt: "" }) : null;
  const text = el(
    "div",
    { class: "text" },
    el("b", { class: toast.ok ? "" : "bad" }, toast.title),
    toast.detail && el("div", { class: "detail" }, toast.detail),
  );

  const card = el("div", { class: "shot-toast" }, picture, text);
  box.replaceChildren(card);
}

async function start() {
  await followTheme();
  await listen("toast", (event) => render(event.payload));
  render(await invoke("toast_content"));
}

start();
