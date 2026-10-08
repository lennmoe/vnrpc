import { el } from "../dom.js";

const NAMED = {
  PrintScreen: "PrintScreen",
  Pause: "Pause",
  Insert: "Insert",
  Home: "Home",
  End: "End",
  PageUp: "PageUp",
  PageDown: "PageDown",
  ScrollLock: "ScrollLock",
  Space: "Space",
  Tab: "Tab",
  ArrowLeft: "Left",
  ArrowUp: "Up",
  ArrowRight: "Right",
  ArrowDown: "Down",
  NumpadMultiply: "NumpadMultiply",
  NumpadAdd: "NumpadAdd",
  NumpadSubtract: "NumpadSubtract",
  NumpadDecimal: "NumpadDecimal",
  NumpadDivide: "NumpadDivide",
};

const MODIFIER_KEYS = ["Control", "Alt", "Shift", "Meta"];

function keyName(event) {
  const code = event.code;

  if (/^Key[A-Z]$/.test(code)) {
    return code.slice(3);
  }
  if (/^Digit\d$/.test(code)) {
    return code.slice(5);
  }
  if (/^F([1-9]|1\d|2[0-4])$/.test(code)) {
    return code;
  }
  if (/^Numpad\d$/.test(code)) {
    return code;
  }
  return NAMED[code] || null;
}

function combination(event) {
  const key = keyName(event);
  if (!key) {
    return null;
  }
  const mods = [];
  if (event.ctrlKey) mods.push("Ctrl");
  if (event.altKey) mods.push("Alt");
  if (event.shiftKey) mods.push("Shift");
  if (event.metaKey) mods.push("Win");
  return [...mods, key].join("+");
}

export function hotkeyInput(value, onChange) {
  const button = el("button", { class: "btn secondary hotkey-btn" });
  let current = value || "";
  let listening = false;

  const showValue = () => {
    button.classList.toggle("listening", listening);
    button.textContent = listening ? "Press a key…" : current || "Off";
  };

  const stop = (newValue) => {
    listening = false;
    window.removeEventListener("keydown", onKeyDown, true);
    window.removeEventListener("keyup", onKeyUp, true);
    if (newValue !== undefined && newValue !== current) {
      current = newValue;
      onChange(current);
    }
    showValue();
  };

  const handle = (event, pressed) => {
    event.preventDefault();
    event.stopPropagation();

    if (event.key === "Escape") {
      return pressed && stop();
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      return pressed && stop("");
    }
    if (MODIFIER_KEYS.includes(event.key)) {
      return;
    }
    if (pressed === (event.code === "PrintScreen")) {
      return;
    }
    const combo = combination(event);
    if (combo) {
      stop(combo);
    }
  };

  const onKeyDown = (event) => handle(event, true);
  const onKeyUp = (event) => handle(event, false);

  button.onclick = () => {
    if (listening) {
      return;
    }
    listening = true;
    button.blur();
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    showValue();
  };

  showValue();
  return button;
}
