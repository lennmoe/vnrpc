use tauri::AppHandle;

use crate::mascot::{self, MascotInfo};
use crate::ui_windows::{self, Toast};

#[tauri::command]
pub fn mascot_info() -> Option<MascotInfo> {
    mascot::info()
}

#[tauri::command]
pub fn mascot_poke(app: AppHandle) {
    mascot::poke(&app);
}

#[tauri::command]
pub fn mascot_open_app(app: AppHandle) {
    ui_windows::show_main(&app);
}

#[tauri::command]
pub fn mascot_menu(app: AppHandle) {
    mascot::show_menu(&app);
}

#[tauri::command]
pub fn balloon_text() -> String {
    ui_windows::balloon_text()
}

#[tauri::command]
pub fn place_balloon(app: AppHandle, width: u32, height: u32) {
    ui_windows::place_balloon(&app, width, height);
}

#[tauri::command]
pub fn hide_balloon(app: AppHandle) {
    ui_windows::hide_balloon(&app);
}

#[tauri::command]
pub fn toast_content() -> Option<Toast> {
    ui_windows::current_toast()
}
