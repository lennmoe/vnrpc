import { el } from "../dom.js";
import { fileUrl } from "../tauri.js";
import { openDialog } from "../ui.js";

export const COVER_ASPECT = 150 / 212;

const STAGE_MAX = 460;
const MIN_SIZE = 12;

export function cropImage({ path, width, height, aspect = COVER_ASPECT }) {
  const scale = Math.min(STAGE_MAX / width, STAGE_MAX / height, 1);
  const stageW = Math.round(width * scale);
  const stageH = Math.round(height * scale);
  const src = fileUrl(path);

  const stage = el("div", {
    class: "crop-stage",
    style: { width: `${stageW}px`, height: `${stageH}px` },
  });
  const dimmed = el("img", { src, alt: "", draggable: "false" });
  const bright = el("img", {
    src,
    alt: "",
    draggable: "false",
    style: { width: `${stageW}px`, height: `${stageH}px` },
  });
  const selection = el("div", { class: "crop-selection" }, bright);
  stage.append(dimmed, selection);

  const lock = el("input", { type: "checkbox", checked: true });
  let rect = { x: 0, y: 0, w: stageW, h: stageH };

  function draw() {
    Object.assign(selection.style, {
      left: `${rect.x}px`,
      top: `${rect.y}px`,
      width: `${rect.w}px`,
      height: `${rect.h}px`,
    });
    bright.style.left = `${-rect.x}px`;
    bright.style.top = `${-rect.y}px`;
  }

  function selectAll() {
    if (!lock.checked) {
      rect = { x: 0, y: 0, w: stageW, h: stageH };
    } else if (stageW / stageH > aspect) {
      const w = stageH * aspect;
      rect = { x: (stageW - w) / 2, y: 0, w, h: stageH };
    } else {
      const h = stageW / aspect;
      rect = { x: 0, y: (stageH - h) / 2, w: stageW, h };
    }
    draw();
  }

  const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

  let drag = null;

  function pointer(event) {
    const box = stage.getBoundingClientRect();
    return {
      x: clamp(event.clientX - box.left, 0, stageW),
      y: clamp(event.clientY - box.top, 0, stageH),
    };
  }

  stage.addEventListener("pointerdown", (event) => {
    stage.setPointerCapture(event.pointerId);
    const p = pointer(event);
    const inside =
      p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h;
    drag = inside
      ? { mode: "move", from: p, start: { ...rect } }
      : { mode: "draw", from: p, previous: { ...rect } };
  });

  stage.addEventListener("pointermove", (event) => {
    if (!drag) {
      return;
    }
    const p = pointer(event);

    if (drag.mode === "move") {
      rect.x = clamp(drag.start.x + p.x - drag.from.x, 0, stageW - rect.w);
      rect.y = clamp(drag.start.y + p.y - drag.from.y, 0, stageH - rect.h);
    } else {
      let w = Math.abs(p.x - drag.from.x);
      let h = Math.abs(p.y - drag.from.y);
      if (lock.checked) {
        if (w / Math.max(h, 1) > aspect) {
          h = w / aspect;
        } else {
          w = h * aspect;
        }
        const roomX = p.x >= drag.from.x ? stageW - drag.from.x : drag.from.x;
        const roomY = p.y >= drag.from.y ? stageH - drag.from.y : drag.from.y;
        const fit = Math.min(1, roomX / Math.max(w, 1), roomY / Math.max(h, 1));
        w *= fit;
        h *= fit;
      }
      const x = p.x >= drag.from.x ? drag.from.x : drag.from.x - w;
      const y = p.y >= drag.from.y ? drag.from.y : drag.from.y - h;
      rect = { x, y, w, h };
    }
    draw();
  });

  stage.addEventListener("pointerup", () => {
    if (drag?.mode === "draw" && (rect.w < MIN_SIZE || rect.h < MIN_SIZE)) {
      rect = drag.previous;
      draw();
    }
    drag = null;
  });

  lock.onchange = selectAll;
  selectAll();

  const reset = el("button", { class: "btn secondary small", onclick: selectAll }, "Reset");
  const body = el(
    "div",
    {},
    stage,
    el(
      "p",
      { class: "muted small-text", style: { textAlign: "center" } },
      "Drag to select · drag inside the selection to move it",
    ),
    el(
      "div",
      { class: "row spread" },
      el("label", { class: "row" }, lock, "Lock cover ratio"),
      reset,
    ),
  );

  return openDialog({
    title: "Crop cover",
    body,
    actions: [
      { label: "Cancel", kind: "secondary", value: null },
      { label: "Apply crop", value: "apply" },
    ],
  }).then((answer) => {
    if (answer !== "apply") {
      return null;
    }
    return {
      x: Math.round(rect.x / scale),
      y: Math.round(rect.y / scale),
      width: Math.max(1, Math.round(rect.w / scale)),
      height: Math.max(1, Math.round(rect.h / scale)),
    };
  });
}
