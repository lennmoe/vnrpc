import { invoke, fileUrl, currentWindow } from "../tauri.js";

const DRAG_SLOP = 4;
const DOUBLE_CLICK_MS = 280;

const character = document.getElementById("character");

let pressedAt = null;
let dragging = false;
let clickTimer = null;

async function start() {
  const info = await invoke("mascot_info");
  if (info) {
    character.src = fileUrl(info.file);
  }
}

character.addEventListener("pointerdown", (event) => {
  if (event.button === 0) {
    pressedAt = { x: event.screenX, y: event.screenY };
    dragging = false;
  }
});

character.addEventListener("pointermove", (event) => {
  if (!pressedAt || dragging || !(event.buttons & 1)) {
    return;
  }
  const distance = Math.abs(event.screenX - pressedAt.x) + Math.abs(event.screenY - pressedAt.y);
  if (distance >= DRAG_SLOP) {
    dragging = true;
    invoke("hide_balloon");
    currentWindow().startDragging();
  }
});

character.addEventListener("pointerup", (event) => {
  if (event.button !== 0 || !pressedAt) {
    return;
  }
  pressedAt = null;
  if (dragging) {
    return;
  }

  if (clickTimer) {
    clearTimeout(clickTimer);
    clickTimer = null;
    invoke("mascot_open_app");
    return;
  }
  clickTimer = setTimeout(() => {
    clickTimer = null;
    invoke("mascot_poke");
  }, DOUBLE_CLICK_MS);
});

character.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  invoke("mascot_menu");
});

start();
