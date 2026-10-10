use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::Serialize;
use serde_json::{json, Map, Value};

use super::{blocking, SharedState};
use crate::images;
use crate::state::{Cmd, Shared};
use crate::vndb::{ReleaseCover, VnResult};

fn apply(shared: &Shared, key: &str, fields: Map<String, Value>) {
    shared.config.lock().unwrap().set_game(key, fields);
    shared.send(Cmd::Reload);
    shared.emit("library-changed", json!({ "key": key }));
}

fn fields(pairs: &[(&str, &str)]) -> Map<String, Value> {
    pairs
        .iter()
        .map(|(k, v)| (k.to_string(), json!(v)))
        .collect()
}

#[tauri::command]
pub async fn search_vndb(shared: SharedState<'_>, query: String) -> Result<Vec<VnResult>, String> {
    let shared = Arc::clone(&shared);
    blocking(move || shared.vndb.search(&query, 12)).await
}

#[tauri::command]
pub async fn release_covers(
    shared: SharedState<'_>,
    vn_id: String,
) -> Result<Vec<ReleaseCover>, String> {
    let shared = Arc::clone(&shared);
    blocking(move || shared.vndb.release_covers(&vn_id)).await
}

#[tauri::command(async)]
pub fn set_game_vn(shared: SharedState, key: String, vn_id: String, title: String) {
    let pairs = [
        ("vndb_id", vn_id.as_str()),
        ("title", &title),
        ("cover_source", "vndb"),
        ("cover_value", &vn_id),
    ];
    apply(&shared, &key, fields(&pairs));
}

#[tauri::command(async)]
pub fn set_release_cover(
    shared: SharedState,
    key: String,
    vn_id: String,
    title: String,
    url: String,
) {
    let pairs = [
        ("vndb_id", vn_id.as_str()),
        ("title", &title),
        ("cover_source", "url"),
        ("cover_value", &url),
    ];
    apply(&shared, &key, fields(&pairs));
}

#[tauri::command(async)]
pub fn set_cover_url(shared: SharedState, key: String, url: String) -> Result<(), String> {
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return Err("Enter a http(s) image link.".into());
    }
    apply(
        &shared,
        &key,
        fields(&[("cover_source", "url"), ("cover_value", &url)]),
    );
    Ok(())
}

#[tauri::command(async)]
pub fn set_cover_file(shared: SharedState, key: String, path: String) -> Result<(), String> {
    let covers_dir = shared.config.lock().unwrap().covers_dir();
    let stored = images::store_local_cover(&covers_dir, Path::new(&path))?;
    let stored = stored.to_string_lossy().to_string();
    apply(
        &shared,
        &key,
        fields(&[("cover_source", "local"), ("cover_value", &stored)]),
    );
    Ok(())
}

#[derive(Serialize)]
pub struct PreparedImage {
    path: String,
    width: u32,
    height: u32,
}

#[tauri::command]
pub async fn prepare_image(
    shared: SharedState<'_>,
    source: String,
) -> Result<PreparedImage, String> {
    let shared = Arc::clone(&shared);
    blocking(move || {
        let downloads = shared.data_dir.join("cache").join("downloads");

        let path: PathBuf = if source.starts_with("http://") || source.starts_with("https://") {
            let bytes = shared
                .vndb
                .download(&source)
                .map_err(|e| format!("couldn't download it: {e}"))?;
            images::store_download(&downloads, &source, &bytes)?
        } else {
            let bytes = std::fs::read(&source).map_err(|e| e.to_string())?;
            images::store_download(&downloads, &source, &bytes)?
        };

        let (width, height) = image::image_dimensions(&path).map_err(|e| e.to_string())?;
        Ok(PreparedImage {
            path: path.to_string_lossy().to_string(),
            width,
            height,
        })
    })
    .await
}
