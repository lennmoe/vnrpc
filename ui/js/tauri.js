const tauri = window.__TAURI__;

export const invoke = tauri.core.invoke;
export const listen = tauri.event.listen;
export const currentWindow = () => tauri.window.getCurrentWindow();

export function fileUrl(path) {
  return path ? tauri.core.convertFileSrc(path) : "";
}

export function pickFile({ title, filters, defaultPath } = {}) {
  return tauri.dialog.open({ title, filters, defaultPath, multiple: false, directory: false });
}

export function pickFolder({ title, defaultPath } = {}) {
  return tauri.dialog.open({ title, defaultPath, directory: true, multiple: false });
}

export function pickSaveFile({ title, filters, defaultPath } = {}) {
  return tauri.dialog.save({ title, filters, defaultPath });
}
