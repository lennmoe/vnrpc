use std::collections::HashSet;
use std::sync::{Arc, Mutex};

use serde_json::{json, Map, Value};

use crate::state::Shared;
use crate::vndb::push_list_status;

static SYNCING: Mutex<Option<HashSet<String>>> = Mutex::new(None);

fn token(shared: &Shared) -> String {
    shared
        .config
        .lock()
        .unwrap()
        .str("vndb_token")
        .trim()
        .to_string()
}

pub fn sync_status(
    shared: &Arc<Shared>,
    key: &str,
    vn_id: &str,
    status: &str,
    keep_existing: bool,
) {
    let token = token(shared);
    let enabled = shared.config.lock().unwrap().bool("vndb_sync");
    if !enabled || token.is_empty() {
        return;
    }

    {
        let mut syncing = SYNCING.lock().unwrap();
        let syncing = syncing.get_or_insert_with(HashSet::new);
        if !syncing.insert(vn_id.to_string()) {
            return;
        }
    }

    let shared = Arc::clone(shared);
    let (key, vn_id, status) = (key.to_string(), vn_id.to_string(), status.to_string());
    std::thread::spawn(move || {
        let result = push_list_status(&shared.vndb, &token, &vn_id, &status, keep_existing);
        SYNCING
            .lock()
            .unwrap()
            .get_or_insert_with(HashSet::new)
            .remove(&vn_id);

        let now = match result {
            Ok(now) => now,
            Err(e) => {
                shared.vndb_message(false, format!("VNDB list sync failed: {e}"));
                return;
            }
        };

        let mut fields = Map::new();
        fields.insert("vndb_synced".into(), json!(vn_id));
        if now != status {
            fields.insert("status".into(), json!(now));
        }
        shared.config.lock().unwrap().set_game(&key, fields);

        let shown = if now.is_empty() {
            "no status".to_string()
        } else {
            capitalize(&now)
        };
        shared.vndb_message(true, format!("VNDB list: {vn_id} → {shown}"));
        shared.emit("library-changed", json!({ "key": key }));
    });
}

fn capitalize(text: &str) -> String {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

fn rating_target(shared: &Shared, key: &str) -> Result<(String, String), String> {
    let token = token(shared);
    let vn_id = shared
        .config
        .lock()
        .unwrap()
        .game(key)
        .get("vndb_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();

    if token.is_empty() {
        return Err("add your VNDB token in Settings first".into());
    }
    if vn_id.is_empty() {
        return Err("confirm this VN's VNDB entry first".into());
    }
    Ok((token, vn_id))
}

pub fn vote(shared: &Shared, key: &str) -> Result<Option<i64>, String> {
    let (token, vn_id) = rating_target(shared, key)?;
    let entry = shared.vndb.list_entry(&token, &vn_id)?;
    let vote = entry.and_then(|e| e["vote"].as_i64()).filter(|v| *v > 0);

    let fields = Map::from_iter([("vndb_vote".into(), json!(vote.unwrap_or(0)))]);
    shared.config.lock().unwrap().set_game(key, fields);
    Ok(vote)
}

pub fn set_vote(shared: &Shared, key: &str, vote: Option<i64>) -> Result<(), String> {
    let (token, vn_id) = rating_target(shared, key)?;
    if let Some(v) = vote {
        if !(10..=100).contains(&v) {
            return Err(format!("a VNDB rating is 10-100, not {v}"));
        }
    }

    shared
        .vndb
        .update_list_entry(&token, &vn_id, &json!({ "vote": vote }))?;
    let fields = Map::from_iter([("vndb_vote".into(), json!(vote.unwrap_or(0)))]);
    shared.config.lock().unwrap().set_game(key, fields);
    Ok(())
}
