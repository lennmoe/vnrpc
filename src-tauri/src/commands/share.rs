use std::path::Path;
use std::sync::Arc;

use base64::Engine as _;
use serde_json::{json, Map, Value};

use super::library::visible_games;
use super::{blocking, SharedState};
use crate::{clipboard, images, screenshots};

#[tauri::command(async)]
pub fn share_games(shared: SharedState) -> Vec<Value> {
    let cfg = shared.config.lock().unwrap();

    visible_games(&cfg)
        .into_iter()
        .map(|(key, entry)| {
            json!({
                "key": key,
                "name": screenshots::display_name(&key, &entry),
                "daily": entry.get("daily").cloned().unwrap_or(json!({})),
                "status": entry.get("status").cloned().unwrap_or(json!("")),
                "finished_at": entry.get("finished_at").cloned().unwrap_or(Value::Null),
                "last_played": entry.get("last_played").cloned().unwrap_or(Value::Null),
                "nsfw": entry.get("cover_nsfw").cloned().unwrap_or(Value::Null),
                "cover": cfg.cached_cover(&entry).map(|p| p.to_string_lossy().to_string()),
            })
        })
        .collect()
}

#[tauri::command]
pub async fn learn_cover_nsfw(
    shared: SharedState<'_>,
    keys: Vec<String>,
) -> Result<Map<String, Value>, String> {
    let shared = Arc::clone(&shared);
    blocking(move || {
        let mut learned = Map::new();
        for key in keys {
            let entry = shared.config.lock().unwrap().game(&key);
            let source = entry
                .get("cover_source")
                .and_then(Value::as_str)
                .unwrap_or("");
            let vn_id = ["vndb_id", "matched_vndb_id"]
                .iter()
                .find_map(|f| {
                    entry
                        .get(*f)
                        .and_then(Value::as_str)
                        .filter(|id| !id.is_empty())
                })
                .map(str::to_string);

            let Some(vn_id) = vn_id else { continue };
            if entry.contains_key("cover_nsfw") || source == "local" || source == "url" {
                continue;
            }

            if let Ok(Some(vn)) = shared.vndb.get(&vn_id) {
                let fields = Map::from_iter([("cover_nsfw".into(), json!(vn.nsfw))]);
                shared.config.lock().unwrap().set_game(&key, fields);
                learned.insert(key, json!(vn.nsfw));
            }
        }
        Ok(learned)
    })
    .await
}

#[tauri::command]
pub async fn image_data_url(path: String, width: u32, height: u32) -> Result<String, String> {
    blocking(move || images::data_url(Path::new(&path), width, height)).await
}

fn decode_png(data_url: &str) -> Result<Vec<u8>, String> {
    let encoded = data_url
        .split_once(',')
        .map(|(_, data)| data)
        .unwrap_or(data_url);
    base64::engine::general_purpose::STANDARD
        .decode(encoded)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn copy_png(data_url: String) -> Result<(), String> {
    blocking(move || clipboard::copy_png(&decode_png(&data_url)?)).await
}

#[tauri::command]
pub async fn save_png(path: String, data_url: String) -> Result<(), String> {
    blocking(move || std::fs::write(&path, decode_png(&data_url)?).map_err(|e| e.to_string())).await
}
