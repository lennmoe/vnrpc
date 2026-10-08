const listeners = new Map();

export const store = {
  version: "",
  settings: {},
  snapshot: {},
  status: {},
  dataDir: "",
  autostart: false,
  screenshotRoot: "",
  defaultScreenshotRoot: "",
};

export function update(part, value) {
  store[part] = value;
  for (const callback of listeners.get(part) || []) {
    callback(value);
  }
}

export function subscribe(part, callback) {
  if (!listeners.has(part)) {
    listeners.set(part, []);
  }
  listeners.get(part).push(callback);
}
