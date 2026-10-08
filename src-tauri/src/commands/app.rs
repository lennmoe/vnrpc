use std::sync::Arc;

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Manager};

use super::{blocking, SharedState};
use crate::engines::{normalize_exe, BUILTIN_BLACKLIST};
use crate::state::{Cmd, Shared};
use crate::{autostart, discord, hotkey, mascot, screenshots, shell, ui_windows, updater, winapi};

pub fn allow_screenshot_folder(shared: &Shared) {
    let root = screenshots::root(&shared.config.lock().unwrap());
    let _ = std::fs::create_dir_all(&root);
    let _ = shared
        .app
        .asset_protocol_scope()
        .allow_directory(&root, true);
}

#[tauri::command(async)]
pub fn get_state(shared: SharedState) -> Value {
    let cfg = shared.config.lock().unwrap();
    json!({
        "version": updater::CURRENT,
        "snapshot": shared.snapshot(),
        "status": shared.status(),
        "settings": cfg.data(),
        "data_dir": cfg.dir.to_string_lossy(),
        "autostart": autostart::is_enabled(),
        "screenshot_root": screenshots::root(&cfg).to_string_lossy(),
        "default_screenshot_root": screenshots::default_root().to_string_lossy(),
        "pending_page": ui_windows::take_pending_page(),
    })
}

#[tauri::command(async)]
pub fn update_settings(
    shared: SharedState,
    app: AppHandle,
    mut changes: Map<String, Value>,
) -> Result<(), String> {
    if let Some(Value::String(key)) = changes.get("screenshot_hotkey") {
        let normalized = hotkey::normalize(key);
        changes.insert("screenshot_hotkey".into(), json!(normalized));
    }
    let mascot_changed = changes.keys().any(|k| k.starts_with("mascot_"));

    shared
        .config
        .lock()
        .unwrap()
        .update(changes)
        .map_err(|e| e.to_string())?;

    shared.send(Cmd::Reload);
    allow_screenshot_folder(&shared);
    if mascot_changed {
        mascot::apply_settings(&app);
    }
    let settings = shared.config.lock().unwrap().data().clone();
    shared.emit("settings-changed", settings);
    Ok(())
}

#[tauri::command(async)]
pub fn set_paused(shared: SharedState, paused: bool) {
    shared.send(Cmd::Pause(paused));
}

#[tauri::command(async)]
pub fn set_autostart(enabled: bool) -> Result<(), String> {
    autostart::set_enabled(enabled)
}

#[tauri::command(async)]
pub fn not_a_vn(shared: SharedState, exe: String) -> Result<(), String> {
    let mut cfg = shared.config.lock().unwrap();
    let mut list: Vec<Value> = cfg
        .get("blacklist_exe")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let wanted = normalize_exe(&exe);
    let already = list
        .iter()
        .any(|v| v.as_str().map(normalize_exe).as_deref() == Some(wanted.as_str()));
    if !already {
        list.push(json!(exe));
    }

    cfg.update(Map::from_iter([(
        "blacklist_exe".into(),
        Value::Array(list),
    )]))
    .map_err(|e| e.to_string())?;
    let settings = cfg.data().clone();
    drop(cfg);

    shared.send(Cmd::Reload);
    shared.emit("settings-changed", settings);
    Ok(())
}

#[tauri::command(async)]
pub fn list_windows() -> Vec<winapi::WindowInfo> {
    winapi::list_top_level_windows()
        .into_iter()
        .filter(|w| !BUILTIN_BLACKLIST.contains(&w.exe().to_lowercase().as_str()))
        .collect()
}

#[tauri::command(async)]
pub fn open_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("only web links can be opened".into());
    }
    shell::open(&url)
}

#[tauri::command]
pub async fn test_discord(client_id: String) -> Result<(), String> {
    if client_id.trim().is_empty() || !client_id.trim().chars().all(|c| c.is_ascii_digit()) {
        return Err("An Application ID is a long number.".into());
    }
    blocking(move || discord::test_connection(client_id.trim())).await
}

#[tauri::command]
pub async fn check_vndb_token(shared: SharedState<'_>, token: String) -> Result<String, String> {
    let shared = Arc::clone(&shared);
    blocking(move || {
        let user = shared.vndb.list_user(token.trim())?;
        Ok(user["username"].as_str().unwrap_or("").to_string())
    })
    .await
}

#[tauri::command(async)]
pub fn take_screenshot(shared: SharedState) {
    let shared = Arc::clone(&shared);
    std::thread::spawn(move || screenshots::take(&shared));
}

#[tauri::command(async)]
pub fn play_shutter(shared: SharedState, volume: i64) {
    crate::sound::play_shutter(&shared.data_dir.join("cache"), volume);
}

#[tauri::command]
pub fn quit(shared: SharedState, app: AppHandle) {
    quit_app(&app, &shared);
}

pub fn quit_app(app: &AppHandle, shared: &Shared) {
    shared.send(Cmd::Quit);
    std::thread::sleep(std::time::Duration::from_millis(400));
    app.exit(0);
}
