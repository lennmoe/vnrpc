import { $, el } from "./dom.js";
import { invoke, fileUrl } from "./tauri.js";
import { store } from "./store.js";

let toastTimer = null;

export function toast(text, { error = false } = {}) {
  const box = $("#toast");
  box.textContent = text;
  box.classList.toggle("error", error);
  box.classList.add("show");

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove("show"), 2800);
}

export async function call(command, args) {
  try {
    return await invoke(command, args);
  } catch (error) {
    toast(typeof error === "string" ? error : error?.detail || JSON.stringify(error), {
      error: true,
    });
    throw error;
  }
}

export function segmented(container, value, onPick) {
  for (const button of container.querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.v === value);
    button.onclick = () => onPick(button.dataset.v);
  }
}

export function toggle(label, checked, onChange, hint = "") {
  const input = el("input", { type: "checkbox" });
  input.checked = !!checked;
  input.onchange = () => onChange(input.checked);

  return el(
    "label",
    { class: "toggle" },
    input,
    el("span", { class: "knob" }),
    el("span", {}, label, hint && el("span", { class: "hint" }, hint)),
  );
}

export function confirmButton(button, label, action) {
  button.textContent = label;
  delete button.dataset.armed;

  button.onclick = (event) => {
    event.stopPropagation();
    if (button.dataset.armed) {
      delete button.dataset.armed;
      return action();
    }
    button.dataset.armed = "1";
    button.textContent = "Click again to confirm";
    setTimeout(() => {
      delete button.dataset.armed;
      button.textContent = label;
    }, 3000);
  };
}

export function flashLabel(button, text, label) {
  button.textContent = text;
  setTimeout(() => (button.textContent = label), 1400);
}

export function setCover(box, { path = "", url = "", nsfw = false, label = "" } = {}) {
  box.replaceChildren();
  box.classList.toggle("nsfw", !!nsfw && !store.settings.allow_nsfw_covers);

  const src = path ? fileUrl(path) : url;
  if (!src) {
    box.append(el("span", {}, initials(label)));
    return;
  }

  const img = el("img", { class: "loading", alt: "", draggable: "false" });
  img.onload = () => img.classList.remove("loading");
  img.onerror = () => setCover(box, { label });
  img.src = src;
  box.append(img);
}

function initials(label) {
  return label ? label.trim().slice(0, 2).toUpperCase() : "VN";
}

export function openDialog({
  title = "",
  body = null,
  actions = [{ label: "OK", value: true }],
  wide = false,
  onOpen = null,
}) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { style: wide ? { width: "min(760px, 92vw)" } : {} });

    const finish = (value) => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };

    const buttons = actions.map((action) =>
      el(
        "button",
        { class: `btn ${action.kind || ""}`, onclick: () => finish(action.value) },
        action.label,
      ),
    );

    dialog.append(
      el("div", { class: "dialog-body" }, title && el("h3", {}, title), body),
      el("div", { class: "dialog-actions" }, buttons),
    );
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(null);
    });

    document.body.append(dialog);
    dialog.showModal();
    onOpen?.(finish);
  });
}

export async function ask(title, message, { yes = "Yes", no = "Cancel", danger = false } = {}) {
  const answer = await openDialog({
    title,
    body: el("p", { class: "muted" }, message),
    actions: [
      { label: no, kind: "secondary", value: false },
      { label: yes, kind: danger ? "danger" : "", value: true },
    ],
  });
  return answer === true;
}
