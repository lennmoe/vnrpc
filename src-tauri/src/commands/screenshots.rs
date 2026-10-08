use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use super::{blocking, SharedState};
use crate::screenshots::{self, ShotInfo};
use crate::{clipboard, images, shell};

#[tauri::command(async)]
pub fn list_screenshots(shared: SharedState, key: Option<String>) -> Value {
    let mut cfg = shared.config.lock().unwrap();
    let games = screenshots::games_with_shots(&mut cfg);

    let extra_name = key
        .as_ref()
        .filter(|k| !games.iter().any(|g| &g.key == *k))
        .map(|k| screenshots::display_name(k, &cfg.game(k)));

    json!({
        "games": games,
        "extra": key.zip(extra_name).map(|(key, name)| json!({ "key": key, "name": name })),
        "root": screenshots::root(&cfg).to_string_lossy(),
        "hotkey": cfg.str("screenshot_hotkey"),
    })
}

#[tauri::command(async)]
pub fn screenshot_info(path: String) -> ShotInfo {
    screenshots::info(Path::new(&path))
}

#[tauri::command]
pub async fn thumbnail(
    shared: SharedState<'_>,
    path: String,
    width: u32,
    height: u32,
) -> Result<String, String> {
    let thumbs = shared.data_dir.join("cache").join("thumbs");
    blocking(move || {
        let thumb = images::thumbnail(&thumbs, Path::new(&path), width, height)?;
        Ok(thumb.to_string_lossy().to_string())
    })
    .await
}

fn inside_root(shared: &SharedState, path: &Path) -> bool {
    let root = screenshots::root(&shared.config.lock().unwrap());
    let canonical = |p: &Path| std::fs::canonicalize(p).unwrap_or_else(|_| p.to_path_buf());
    canonical(path).starts_with(canonical(&root))
}

#[tauri::command(async)]
pub fn delete_screenshot(shared: SharedState, key: String, path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    if !inside_root(&shared, &path) {
        return Err("that file isn't in the screenshots folder".into());
    }
    shell::send_to_recycle_bin(&path)?;
    shared.emit("screenshots-changed", json!({ "key": key }));
    Ok(())
}

#[tauri::command]
pub async fn copy_image_file(path: String) -> Result<(), String> {
    blocking(move || {
        let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
        let is_png = bytes.starts_with(&[0x89, b'P', b'N', b'G']);
        if is_png {
            return clipboard::copy_png(&bytes);
        }

        let img = image::load_from_memory(&bytes).map_err(|e| e.to_string())?;
        let mut png = Vec::new();
        img.write_to(&mut std::io::Cursor::new(&mut png), image::ImageFormat::Png)
            .map_err(|e| e.to_string())?;
        clipboard::copy_png(&png)
    })
    .await
}

#[tauri::command(async)]
pub fn open_path(path: String) -> Result<(), String> {
    shell::open(&path)
}

#[tauri::command(async)]
pub fn show_in_folder(path: String) -> Result<(), String> {
    shell::show_in_folder(Path::new(&path))
}

#[tauri::command(async)]
pub fn open_screenshot_folder(shared: SharedState, key: Option<String>) -> Result<(), String> {
    let folder = {
        let mut cfg = shared.config.lock().unwrap();
        key.and_then(|k| screenshots::folder_for(&mut cfg, &k, false))
            .filter(|f| f.is_dir())
            .unwrap_or_else(|| screenshots::root(&cfg))
    };
    std::fs::create_dir_all(&folder).map_err(|e| e.to_string())?;
    shell::open(&folder.to_string_lossy())
}
