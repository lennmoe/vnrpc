use std::path::PathBuf;
use std::sync::Arc;

use serde_json::Value;
use tauri::AppHandle;

use super::app::{allow_screenshot_folder, quit_app};
use super::{blocking, SharedState};
use crate::state::Cmd;
use crate::updater::{self, Notes, Release};
use crate::{backup, mascot};

#[tauri::command(async)]
pub fn backup_default_name() -> String {
    backup::default_name()
}

#[tauri::command]
pub async fn export_data(shared: SharedState<'_>, path: String) -> Result<usize, String> {
    let shared = Arc::clone(&shared);
    blocking(move || backup::export(&shared.config.lock().unwrap(), &PathBuf::from(path))).await
}

#[tauri::command]
pub async fn import_data(
    shared: SharedState<'_>,
    app: AppHandle,
    path: String,
) -> Result<usize, String> {
    let shared = Arc::clone(&shared);
    let count = {
        let shared = Arc::clone(&shared);
        blocking(move || backup::import(&mut shared.config.lock().unwrap(), &PathBuf::from(path)))
            .await?
    };

    shared.send(Cmd::Reload);
    allow_screenshot_folder(&shared);
    mascot::apply_settings(&app);
    let settings: Value = shared.config.lock().unwrap().data().clone().into();
    shared.emit("settings-changed", settings);
    shared.emit("library-changed", serde_json::json!({}));
    Ok(count)
}

#[tauri::command(async)]
pub fn backup_folder(shared: SharedState) -> String {
    backup::backup_dir(&shared.config.lock().unwrap())
        .to_string_lossy()
        .to_string()
}

#[tauri::command]
pub async fn check_update() -> Result<Option<Release>, String> {
    blocking(updater::find_update).await
}

#[tauri::command]
pub async fn install_update(
    shared: SharedState<'_>,
    app: AppHandle,
    release: Release,
) -> Result<(), String> {
    let path = blocking(move || {
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        match updater::download(&release, &updater::staging_path(&exe)) {
            Ok(path) => Ok(path),
            Err(_) => updater::download(
                &release,
                &std::env::temp_dir().join("VisualNovelRPC.new.exe"),
            ),
        }
    })
    .await?;

    updater::install(&path)?;
    quit_app(&app, &shared);
    Ok(())
}

#[tauri::command]
pub async fn release_notes() -> Result<Vec<Notes>, String> {
    blocking(updater::release_notes).await
}
